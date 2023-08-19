# automatically add __annotations__ to objects using static analysis & mypy.

from __future__ import annotations

import ast
import contextlib
import importlib
import inspect
import io
import re
from collections import ChainMap
from collections.abc import Callable, Generator
from importlib import reload
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Union

import mypy  # Remove compiled mypy files  # https://github.com/mypyc/mypyc/issues/754

for file in Path(mypy.__file__).parent.rglob("*.so"):
    file.unlink()


reload(mypy)
from mypy import nodes, types
from mypy.build import BuildSource, build
from mypy.options import Options
from mypy.type_visitor import TypeVisitor
from sphinx.util.inspect import isenumclass

from docs.extensions import ROOT

if TYPE_CHECKING:
    from types import GenericAlias

    from sphinx.application import Sphinx


class NullIO(io.IOBase):
    def write(self, *_, **__) -> None:
        ...


options = Options()
options.export_types = True
cache: dict[str, ChainMap[nodes.Expression, types.Type]] = {}

stdout = stderr = NullIO()
MISSING = object()
LiteralGenericAlias = type(Literal[0])


class TypeEvalVisitor(TypeVisitor[Any]):
    # fmt: off
    visit_uninhabited_type = visit_erased_type = visit_deleted_type = visit_typeddict_type = \
    visit_partial_type = visit_type_guard_type = visit_unbound_type = lambda *args, **kwargs: MISSING
    # fmt: on

    def visit_simple_type(self, type: type, types: list[types.Type]) -> GenericAlias:
        return type[self.collect_types(types)]

    def collect_types(self, types: list[types.Type]) -> tuple[Any, ...]:
        args = []
        for type in types:
            accepted = type.accept(self)
            if accepted is not MISSING:
                args.append(accepted)

        return tuple(args)

    def get(self, name: str) -> Any:
        module, _, name = name.rpartition(".")
        try:
            return getattr(importlib.import_module(module), name)
        except AttributeError:
            return MISSING

    def visit_none_type(self, type: types.NoneType) -> None:
        return None

    def visit_any(self, t: types.AnyType) -> Any:
        return Any

    def visit_overloaded(self, t: types.Overloaded) -> GenericAlias:
        return Union[self.collect_types(t.items)]

    def visit_callable_type(self, t: types.CallableType) -> GenericAlias:
        return Callable[list(self.collect_types(t.arg_types)), self.collect_types([t.ret_type])[0]]

    def visit_literal_type(self, t: types.LiteralType) -> GenericAlias:
        value = t.value_repr()
        try:
            return Literal[ast.literal_eval(value)]  # this isn't really necessary
        except NameError:  # enum
            return Literal[self.get(value)]

    def visit_type_var(self, t: types.TypeVarType) -> Any:
        return self.get(t.fullname)

    def visit_instance(self, t: types.Instance) -> Any:
        instance = self.get(t.type.fullname)
        args = self.collect_types(t.args)
        if args and not all(isinstance(arg, types.AnyType) for arg in args):
            try:
                instance = instance[args]  # construct a generic alias
            except Exception:
                pass
        return instance

    def visit_tuple_type(self, t: types.TupleType) -> GenericAlias:
        return self.visit_simple_type(tuple, t.items)

    def visit_type_type(self, t: types.TypeType) -> GenericAlias:
        return self.visit_simple_type(type, [t.item])

    def visit_union_type(self, t: types.UnionType) -> Any:
        if len(t.items) == 1:
            return t.items[0]
        if all(isinstance(arg, LiteralGenericAlias) for arg in t.items):
            return Literal[tuple(t.__args__[0] for t in self.collect_types(t.items))]
        return Union[self.collect_types(t.items)]

    def visit_type_alias_type(self, t: types.TypeAliasType) -> Any:
        return t.expand_all_if_possible().accept(self) if not t.is_recursive else self.get(t.alias.fullname)


@contextlib.contextmanager
def load_module(module: str) -> Generator[ChainMap[nodes.Expression, types.Type], None, None]:
    if not module.startswith("steam"):  # typing_extensions.TypeAlias
        yield ChainMap()
        return

    try:
        yield cache[module]
        return
    except KeyError:
        pass

    mod = importlib.import_module(module)

    path = ROOT / f"{module.replace('.', '/')}.py"
    original = path.read_text()

    path.write_text(f"{original}\n\n_: int = '1'")  # needed to make sure .types works, TODO make an issue about this?

    try:
        result = build([BuildSource(mod.__file__, mod.__name__)], options, stdout=stdout, stderr=stderr)
        types = result.types

        for file in result.files.values():
            cache[file.fullname] = ChainMap({func.node: func.type for func in file.names.values()}, types)

        yield cache[module]
    finally:
        path.write_text(original)


def get_annotations(object: object, what: str, name: str) -> Generator[tuple[str, Any], None, None]:
    with load_module(object.__module__) as type_map:
        if isinstance(object, type):
            for expr in type_map:
                if (
                    isinstance(expr, (nodes.NameExpr, nodes.MemberExpr))
                    and isinstance(expr.node, nodes.Var)
                    and not expr.name.startswith("_")
                    and f"{object.__module__}.{object.__name__}" == (expr.node.fullname or "").rpartition(".")[0]
                    and expr.node.type
                ):
                    yield expr.name, expr.node.type.accept(TypeEvalVisitor())
        elif callable(object):
            is_coroutine = inspect.iscoroutinefunction(object)
            if what == "method":
                fullname = f"{object.__module__}.{re.findall(r'([A-Z].*)', name)[0]}"

            for node, type_ in type_map.items():
                if what == "method":
                    if not isinstance(node, nodes.TypeInfo) or fullname.rpartition(".")[0] != node.fullname:
                        continue
                    method = node[object.__name__]
                    is_static = isinstance(object, staticmethod)

                    if isinstance(method.type, types.CallableType):
                        return_type = method.type.ret_type.args[-1] if is_coroutine else method.type.ret_type
                        names = method.type.arg_names[1 if not is_static else 0 :]
                        arg_types = method.type.arg_types[1 if not is_static else 0 :]
                    elif isinstance(method.type, types.Overloaded):
                        items = method.type.items
                        union = types.UnionType(
                            [t.ret_type.args[-1] if is_coroutine else t.ret_type for t in items],
                            uses_pep604_syntax=True,
                        )
                        return_type = union if len(union.items) < 5 else types.AnyType(types.TypeOfAny.explicit)
                        names = []
                        arg_types = []
                        for item in items:
                            names.extend(item.arg_names[1 if not is_static else 0 :])
                            arg_types.extend(item.arg_types[1 if not is_static else 0 :])
                    else:
                        continue
                else:
                    if not isinstance(type_, types.CallableType) or type_.name != object.__name__:
                        continue
                    return_type = type_.ret_type.args[-1] if is_coroutine else type_.ret_type
                    names = type_.arg_names
                    arg_types = type_.arg_types
                yield from zip([*names, "return"], [t.accept(TypeEvalVisitor()) for t in ([*arg_types, return_type])])
                break


def add_annotations(app: Sphinx, what: str, name: str, object: Any, *args: Any) -> None:
    if what not in {"class", "function", "method"} or isenumclass(object):
        return  # can't have annotations

    if isinstance(object, type):
        annotations: dict[str, Any] = {}
        for base in reversed(object.__mro__[:-1]):
            for name, evaled_type in get_annotations(base, what, f"{base.__module__}.{base.__name__}"):
                if evaled_type is MISSING:
                    continue
                try:
                    base.__annotations__[name] = evaled_type
                except AttributeError:  # TODO remove when postponed annotations are available
                    try:
                        base.__annotations__ = {name: evaled_type}
                    except AttributeError:
                        break

            base.__module__ = (
                "steam"
                if base.__module__.startswith("steam") and not base.__module__.endswith(("abc", "guard", "utils"))
                else base.__module__
            )
            try:
                base.__annotations__ = annotations = getattr(base, "__annotations__", {}) | annotations
            except AttributeError:
                pass
    else:
        for name, evaled_type in get_annotations(object, what, name):
            if evaled_type is MISSING:
                continue
            try:
                object.__annotations__[name] = evaled_type
            except AttributeError:  # TODO remove when postponed annotations are available
                try:
                    object.__annotations__ = {name: evaled_type}
                except AttributeError:
                    break


def setup(app: Sphinx) -> None:
    app.connect("autodoc-process-docstring", add_annotations, priority=1)  # should be ran before any other event
