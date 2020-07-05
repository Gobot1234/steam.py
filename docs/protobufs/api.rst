.. currentmodule:: steam.protobufs

API reference
=============

This is documentation for the internal-ish classes used to communicate with
Steam CMs. Most people don't need to use these.


Protobufs
---------

MsgProto
~~~~~~~~

.. autoclass:: steam.protobufs.MsgProto
    :inherited-members:
    :members:

Msg
~~~~~~~~

.. autoclass:: steam.protobufs.Msg
    :inherited-members:
    :members:


Headers
~~~~~~~~

.. autoclass:: steam.protobufs.headers.MsgHdr
    :members:

.. autoclass:: steam.protobufs.headers.ExtendedMsgHdr
    :members:

.. autoclass:: steam.protobufs.headers.MsgHdrProtoBuf
    :members:


Get methods
-----------

.. autofunction:: steam.protobufs.get_cmsg

.. autofunction:: steam.protobufs.get_um
