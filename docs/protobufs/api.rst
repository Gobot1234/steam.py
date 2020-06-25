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
    :members:

Msg
~~~~~~~~

.. autoclass:: steam.protobufs.Msg
    :members:


Headers
~~~~~~~~

.. automodule:: steam.protobufs.headers.MsgHdr
    :members:

.. automodule:: steam.protobufs.headers.ExtendedMsgHdr
    :members:

.. automodule:: steam.protobufs.headers.MsgHdrProtoBuf
    :members:

.. automodule:: steam.protobufs.headers.GCMsgHdr
    :members:

.. automodule:: steam.protobufs.headers.GCMsgHdrProto
    :members:


Get methods
-----------

.. autofunction:: steam.protobufs.get_cmsg

.. autofunction:: steam.protobufs.get_um
