.. currentmodule:: steam

API reference
=============

The following document outlines the front facing aspects of steam.py.

.. note::
    This module uses Python's logging module to debug, give information and diagnose errors, it is recommended to
    configure this if necessary as errors or warnings will not be propagated properly.

Version Related Info
---------------------

.. data:: __version__

    A string representation of the version. e.g. ``'0.1.3'``. This is based off of :pep:`440`.

.. data:: version_info

    A :class:`typing.NamedTuple` similar to :obj:`sys.version_info` except without a serial field.

Client
------

.. attributetable:: Client

.. autoclass:: Client
    :members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error,
                      on_message, on_typing,
                      on_trade_receive, on_trade_send, on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment,
                      on_user_invite, on_user_invite_accept, on_user_invite_decline, on_friend_add, on_user_update,
                      on_friend_remove,
                      on_clan_invite, on_clan_invite_accept, on_clan_invite_decline, on_clan_join, on_clan_update,
                      on_clan_leave,
                      on_group_join, on_group_update, on_group_leave,
                      on_event_create, on_announcement_create,
                      on_socket_receive, on_socket_send


.. _event-reference:

Event Reference
---------------

This page outlines the different types of events listened for by the :class:`Client`.

There are two ways to register an event, the first way is through the use of :meth:`Client.event`. The second way is
through subclassing :class:`Client` and overriding the specific events. For example: ::

    import steam


    class MyClient(steam.Client):
        async def on_trade_receive(self, trade: steam.TradeOffer) -> None:
            await trade.partner.send('Thank you for your trade')
            print(f'Received trade: #{trade.id}')
            print('Trade partner is:', trade.partner)
            print('We would send:', len(trade.sending), 'items')
            print('We would receive:', len(trade.receiving), 'items')

            if trade.is_gift():
                print('Accepting the trade as it is a gift')
                await trade.accept()


If an event handler raises an exception, :meth:`Client.on_error` will be called to handle it, which by default prints a
traceback and ignoring the exception.

.. warning::
    All the events must be a :term:`coroutine function`. If they aren't, a :exc:`TypeError` will be raised.

.. automethod:: Client.on_connect

.. automethod:: Client.on_disconnect

.. automethod:: Client.on_ready

.. automethod:: Client.on_login

.. automethod:: Client.on_error

.. automethod:: Client.on_message

.. automethod:: Client.on_typing

.. automethod:: Client.on_trade_receive

.. automethod:: Client.on_trade_send

.. automethod:: Client.on_trade_accept

.. automethod:: Client.on_trade_decline

.. automethod:: Client.on_trade_cancel

.. automethod:: Client.on_trade_expire

.. automethod:: Client.on_trade_counter

.. automethod:: Client.on_comment

.. automethod:: Client.on_user_invite

.. automethod:: Client.on_user_invite_accept

.. automethod:: Client.on_user_invite_decline

.. automethod:: Client.on_friend_add

.. automethod:: Client.on_user_update

.. automethod:: Client.on_friend_remove

.. automethod:: Client.on_clan_invite

.. automethod:: Client.on_clan_invite_accept

.. automethod:: Client.on_clan_invite_decline

.. automethod:: Client.on_clan_join

.. automethod:: Client.on_clan_update

.. automethod:: Client.on_clan_leave

.. automethod:: Client.on_group_join

.. automethod:: Client.on_group_update

.. automethod:: Client.on_group_leave

.. automethod:: Client.on_event_create

.. automethod:: Client.on_announcement_create

.. automethod:: Client.on_socket_receive

.. automethod:: Client.on_socket_send


Utilities
----------

steam.py provides some utility functions.

.. autofunction:: steam.utils.parse_id64

.. autofunction:: steam.utils.parse_trade_url

Then some functions from discord.py

.. autofunction:: steam.utils.get

.. autofunction:: steam.utils.find


Enumerations
-------------

.. autoclass:: Result()
    :members:
    :undoc-members:

.. autoclass:: Language()
    :members:
    :undoc-members:

.. autoclass:: Universe()
    :members:
    :undoc-members:

.. autoclass:: Type()
    :members:
    :undoc-members:

.. autoclass:: TypeChar()
    :members:
    :undoc-members:

.. autoclass:: Instance()
    :members:
    :undoc-members:

.. autoclass:: FriendRelationship()
    :members:
    :undoc-members:

.. autoclass:: PersonaState()
    :members:
    :undoc-members:

.. autoclass:: PersonaStateFlag()
    :members:
    :undoc-members:

.. autoclass:: CommunityVisibilityState()
    :members:
    :undoc-members:

.. autoclass:: TradeOfferState()
    :members:
    :undoc-members:

.. autoclass:: ChatEntryType()
    :members:
    :undoc-members:

.. autoclass:: UIMode()
    :members:
    :undoc-members:

.. autoclass:: UserBadge()
    :members:
    :undoc-members:

.. autoclass:: ReviewType()
    :members:
    :undoc-members:

.. autoclass:: GameServerRegion()
    :members:
    :undoc-members:

.. autoclass:: EventType()
   :members:
   :undoc-members:

.. autoclass:: ProfileItemType()
   :members:
   :undoc-members:

.. autoclass:: CommunityItemClass()
   :members:
   :undoc-members:

.. autoclass:: DepotFileFlag()
   :members:
   :undoc-members:

.. autoclass:: AppType()
   :members:
   :undoc-members:

.. autoclass:: LicenseFlag()
   :members:
   :undoc-members:

.. autoclass:: LicenseType()
   :members:
   :undoc-members:

.. autoclass:: BillingType()
   :members:
   :undoc-members:

.. autoclass:: PaymentMethod()
   :members:
   :undoc-members:

.. autoclass:: PackageStatus()
   :members:
   :undoc-members:

.. autoclass:: PublishedFileRevision()
   :members:
   :undoc-members:

.. autoclass:: LeaderboardDataRequest()
    :members:
    :undoc-members:

.. autoclass:: LeaderboardSortMethod()
    :members:
    :undoc-members:

.. autoclass:: LeaderboardDisplayType()
    :members:
    :undoc-members:

.. autoclass:: LeaderboardUploadScoreMethod()
    :members:
    :undoc-members:

.. autoclass:: CommunityDefinitionItemType()
    :members:
    :undoc-members:

.. autoclass:: AuthSessionResponse()
    :members:
    :undoc-members:


Guard
---------------

.. autofunction:: steam.guard.generate_one_time_code

.. autofunction:: steam.guard.generate_confirmation_code

.. autofunction:: steam.guard.generate_device_id


Abstract Base Classes
-----------------------

An :term:`abstract base class` (also known as an ``abc``) is a class that models can inherit their behaviour from.

.. attributetable:: steam.abc.BaseUser

.. autoclass:: steam.abc.BaseUser()
    :members:
    :undoc-members:
    :inherited-members:

.. attributetable:: steam.abc.Channel

.. autoclass:: steam.abc.Channel()
    :members:
    :inherited-members:

.. attributetable:: steam.abc.Commentable

.. autoclass:: steam.abc.Commentable()
    :members:
    :inherited-members:

.. attributetable:: steam.abc.Messageable

.. autoclass:: steam.abc.Messageable()
    :members:

Steam Models
---------------

steam.py provides wrappers around common Steam API objects.
These are not meant to be constructed by the user instead you receive them from methods/events.

Achievements
~~~~~~~~~~~~~~~

.. attributetable:: AppStat

.. autoclass:: AppStat()
    :members:
    :inherited-members:

.. attributetable:: UserAppStat

.. autoclass:: UserAppStat()
    :members:
    :inherited-members:

.. attributetable:: AppAchievement

.. autoclass:: AppAchievement()
    :members:
    :inherited-members:

.. attributetable:: AppStatAchievement

.. autoclass:: AppStatAchievement()
    :members:
    :inherited-members:

.. attributetable:: UserAppAchievement

.. autoclass:: UserAppAchievement()
    :members:
    :inherited-members:

.. attributetable:: AppStats

.. autoclass:: AppStats()
    :members:
    :inherited-members:

.. attributetable:: UserAppStats

.. autoclass:: UserAppStats()
    :members:
    :inherited-members:

Announcements
~~~~~~~~~~~~~~~

.. attributetable:: Announcement

.. autoclass:: Announcement
    :members:
    :inherited-members:


Badge
~~~~~~~~~~~~~~~

.. attributetable:: AppBadge

.. autoclass:: AppBadge()
    :members:

.. attributetable:: UserBadge

.. autoclass:: UserBadge()
    :members:

.. attributetable:: UserBadges

.. autoclass:: UserBadges()
    :members:

.. attributetable:: FavouriteBadge

.. autoclass:: FavouriteBadge()
    :members:

Ban
~~~~~~~~~~~~~~~

.. attributetable:: Ban

.. autoclass:: Ban()
    :members:


Bundle
~~~~~~~~~~~~~~~

.. attributetable:: Bundle

.. autoclass:: Bundle()
    :members:

.. attributetable:: PartialBundle

.. autoclass:: PartialBundle()
    :members:

.. attributetable:: FetchedBundle

.. autoclass:: FetchedBundle()
    :members:


Channel
~~~~~~~~~~~~~~~

.. attributetable:: UserChannel

.. autoclass:: UserChannel()
    :members:
    :inherited-members:

.. attributetable:: GroupChannel

.. autoclass:: GroupChannel()
    :members:
    :inherited-members:

.. attributetable:: ClanChannel

.. autoclass:: ClanChannel()
    :members:
    :inherited-members:


Clan
~~~~~~~~~~~~~~~

.. attributetable:: Clan

.. autoclass:: Clan()
    :members:
    :inherited-members:


Comment
~~~~~~~~~~~~~~~

.. attributetable:: Comment

.. autoclass:: Comment()
    :members:


Events
~~~~~~~~~~~~~~~

.. attributetable:: Event

.. autoclass:: Event()
    :members:
    :inherited-members:


Game Servers
~~~~~~~~~~~~~~~

.. attributetable:: GameServer

.. autoclass:: GameServer()
    :members:
    :inherited-members:

.. attributetable:: Query

.. autoclass:: Query()
    :members:


Group
~~~~~~~~~~~~~~~

.. attributetable:: Group

.. autoclass:: Group()
    :members:
    :inherited-members:

Invite
~~~~~~~~~~~~~~~

.. attributetable:: UserInvite

.. autoclass:: UserInvite()
    :members:
    :inherited-members:

.. attributetable:: ClanInvite

.. autoclass:: ClanInvite()
    :members:
    :inherited-members:

Leaderboard
~~~~~~~~~~~~~~~

.. attributetable:: Leaderboard

.. autoclass:: Leaderboard()
    :members:
    :inherited-members:

.. attributetable:: LeaderboardUser

.. autoclass:: LeaderboardUser()
    :members:
    :undoc-members:
    :inherited-members:

.. attributetable:: LeaderboardScoreUpdate

.. autoclass:: LeaderboardScoreUpdate()
    :members:

Manifests
~~~~~~~~~~~~~~~

.. attributetable:: Manifest

.. autoclass:: Manifest()
   :members:

.. attributetable:: ManifestPath

.. autoclass:: ManifestPath()
   :members:
   :inherited-members:

.. attributetable:: Branch

.. autoclass:: Branch()
   :members:

.. attributetable:: ManifestInfo

.. autoclass:: ManifestInfo()
   :members:

.. attributetable:: HeadlessDepot

.. autoclass:: HeadlessDepot()
   :members:

.. attributetable:: Depot

.. autoclass:: Depot()
   :members:
   :inherited-members:

.. attributetable:: AppInfo

.. autoclass:: AppInfo()
   :members:
   :inherited-members:

.. attributetable:: PackageInfo

.. autoclass:: PackageInfo()
   :members:
   :inherited-members:

Message
~~~~~~~~~~~~~~~

.. attributetable:: Message

.. autoclass:: Message()
    :members:

.. attributetable:: UserMessage

.. autoclass:: UserMessage()
    :members:
    :inherited-members:

.. attributetable:: GroupMessage

.. autoclass:: GroupMessage()
    :members:
    :inherited-members:

.. attributetable:: ClanMessage

.. autoclass:: ClanMessage()
    :members:
    :inherited-members:

Package
~~~~~~~~~~~~~~~

.. attributetable:: Package

.. autoclass:: Package()
   :members:

.. attributetable:: steam.package.PartialPackage

.. autoclass:: steam.package.PartialPackage()
   :members:
   :inherited-members:

.. attributetable:: steam.FetchedPackage

.. autoclass:: steam.FetchedPackage()
   :members:
   :inherited-members:

.. attributetable:: License

.. autoclass:: License()
   :members:
   :inherited-members:

.. attributetable:: FetchedAppPackage

.. autoclass:: FetchedAppPackage()
   :members:
   :inherited-members:


Post
~~~~~~~~~~~~~~~

.. attributetable:: Post

.. autoclass:: Post()
    :members:
    :inherited-members:


PriceOverview
~~~~~~~~~~~~~~~

.. attributetable:: PriceOverview

.. autoclass:: PriceOverview()
    :members:

Profile
~~~~~~~~~~~~~~~

.. attributetable:: ProfileInfo

.. autoclass:: ProfileInfo()
    :members:

.. attributetable:: ProfileItem

.. autoclass:: ProfileItem()
    :members:

.. attributetable:: OwnedProfileItems

.. autoclass:: OwnedProfileItems()
    :members:

.. attributetable:: EquippedProfileItems

.. autoclass:: EquippedProfileItems()
    :members:

.. attributetable:: ProfileShowcase

.. autoclass:: ProfileShowcase()
    :members:

.. attributetable:: Profile

.. autoclass:: Profile()
    :members:
    :inherited-members:


PublishedFile
~~~~~~~~~~~~~~~

.. attributetable:: PublishedFile

.. autoclass:: PublishedFile()
    :members:
    :inherited-members:


Store
~~~~~~~~~~~~~~~

.. attributetable:: StoreItem

.. autoclass:: StoreItem()
    :members:
    :inherited-members:

.. attributetable:: AppStoreItem

.. autoclass:: AppStoreItem()
    :members:
    :inherited-members:

.. attributetable:: PackageStoreItem

.. autoclass:: PackageStoreItem()
    :members:
    :inherited-members:

.. attributetable:: BundleStoreItem

.. autoclass:: BundleStoreItem()
    :members:
    :inherited-members:

.. attributetable:: TransactionReceipt

.. autoclass:: TransactionReceipt()
    :members:
    :inherited-members:

App Tickets
~~~~~~~~~~~~~~~

.. attributetable:: EncryptedTicket

.. autoclass:: EncryptedTicket()
    :members:
    :inherited-members:
    :undoc-members:

.. attributetable:: OwnershipTicket

.. autoclass:: OwnershipTicket()
    :members:
    :inherited-members:
    :undoc-members:

.. attributetable:: AuthenticationTicket

.. autoclass:: AuthenticationTicket()
    :members:
    :inherited-members:
    :undoc-members:

Trading
~~~~~~~~~~~~~~~

.. attributetable:: Inventory

.. autoclass:: Inventory()
    :members:
    :inherited-members:

.. attributetable:: Item

.. autoclass:: Item()
    :members:
    :inherited-members:

.. attributetable:: Asset

.. autoclass:: Asset()
    :members:

.. attributetable:: MovedItem

.. autoclass:: MovedItem()
    :members:

Reactions
~~~~~~~~~~~~~~~

.. attributetable:: Award

.. autoclass:: Award()
    :members:
    :inherited-members:

.. attributetable:: AwardReaction

.. autoclass:: AwardReaction()
    :members:
    :inherited-members:

.. attributetable:: PartialMessageReaction

.. autoclass:: PartialMessageReaction()
    :members:
    :inherited-members:

.. attributetable:: MessageReaction

.. autoclass:: MessageReaction()
    :members:
    :inherited-members:

.. attributetable:: Emoticon

.. autoclass:: Emoticon()
    :members:
    :inherited-members:

.. attributetable:: Sticker

.. autoclass:: Sticker()
    :members:
    :inherited-members:

.. attributetable:: ClientEmoticon

.. autoclass:: ClientEmoticon()
    :members:
    :inherited-members:

.. attributetable:: ClientSticker

.. autoclass:: ClientSticker()
    :members:
    :inherited-members:

Reviews
~~~~~~~~~~~~~~~

.. attributetable:: Review

.. autoclass:: Review()
    :members:
    :inherited-members:

.. attributetable:: ReviewUser

.. autoclass:: ReviewUser()
    :members:
    :undoc-members:
    :inherited-members:

Roles
~~~~~~~~~~~~~~~

.. attributetable:: Role

.. autoclass:: Role()
    :members:

.. attributetable:: RolePermissions

.. autoclass:: RolePermissions()
    :members:

Users
~~~~~~~~~~~~~~~

.. attributetable:: PartialUser

.. autoclass:: PartialUser()
    :members:
    :undoc-members:
    :inherited-members:

.. attributetable:: ClientUser

.. autoclass:: ClientUser()
    :members:
    :undoc-members:
    :inherited-members:

.. attributetable:: User

.. autoclass:: User()
    :members:
    :undoc-members:
    :inherited-members:

.. attributetable:: Friend

.. autoclass:: Friend()
    :members:
    :undoc-members:
    :inherited-members:

Wallet
~~~~~~~~~~~~~~~

.. attributetable:: Wallet

.. autoclass:: Wallet()


Data-Classes
---------------

There are a few classes that can be constructed by the user, these include.

App
~~~~~~~~~~~~~~~

.. attributetable:: App

.. autoclass:: App
    :members:

There are some predefined apps which are:

.. autodata:: TF2

.. autodata:: DOTA2

.. autodata:: CSGO

.. autodata:: LFD2

.. autodata:: STEAM

These are shorthand for ``Client.get_game(440)`` etc. (you need a client to have been constructed and be use to use the
methods that they inherit from :class:`PartialApp`), they are also valid as type parameters to :class:`typing.Literal`


Apps can be manually constructed using their app ID eg:

.. code-block:: python3

    my_rust_instance = steam.App(id=252490, name="Rust")
    # this can then be used for trading an app name is not required for this

.. autofunction:: CUSTOM_APP

.. attributetable:: steam.app.PartialApp

.. autoclass:: steam.app.PartialApp()
    :inherited-members:
    :members:

.. attributetable:: UserApp

.. autoclass:: UserApp()
    :inherited-members:
    :members:

.. attributetable:: WishlistApp

.. autoclass:: WishlistApp()
    :inherited-members:
    :members:

.. attributetable:: FetchedApp

.. autoclass:: FetchedApp()
    :inherited-members:
    :members:

.. attributetable:: DLC

.. autoclass:: DLC()
    :inherited-members:
    :members:

.. attributetable:: OwnershipTicket

.. autoclass:: OwnershipTicket()
    :inherited-members:
    :members:

.. attributetable:: AuthenticationTicket

.. autoclass:: AuthenticationTicket()
    :inherited-members:
    :members:

.. attributetable:: EncryptedTicket

.. autoclass:: EncryptedTicket()
    :inherited-members:
    :members:


Steam IDs
~~~~~~~~~~~~~~~

.. attributetable:: ID

.. autoclass:: ID
    :members:

TradeOffers
~~~~~~~~~~~~~~~

.. attributetable:: TradeOffer

.. autoclass:: TradeOffer
    :members:


Images
~~~~~~~~~~~~~~~

.. attributetable:: Image

.. autoclass:: Image
    :members:

Exceptions
------------

The following exceptions are thrown by the library.

.. autoexception:: SteamException

.. autoexception:: ClientException

.. autoexception:: LoginError

.. autoexception:: InvalidCredentials

.. autoexception:: NoCMsFound

.. autoexception:: AuthenticatorError

.. autoexception:: ConfirmationError

.. autoexception:: HTTPException

.. autoexception:: Forbidden

.. autoexception:: NotFound

.. autoexception:: WSException

.. autoexception:: WSForbidden

.. autoexception:: WSNotFound

.. autoexception:: InvalidID



Exception Hierarchy
~~~~~~~~~~~~~~~~~~~~~

.. exception_hierarchy::

    - :exc:`Exception`
        - :exc:`SteamException`
            - :exc:`ClientException`
                - :exc:`AuthenticatorError`
                    - :exc:`ConfirmationError`
                - :exc:`LoginError`
                    - :exc:`InvalidCredentials`
                    - :exc:`NoCMsFound`
            - :exc:`HTTPException`
                - :exc:`Forbidden`
                - :exc:`NotFound`
            - :exc:`WSException`
                - :exc:`WSForbidden`
                - :exc:`WSNotFound`
            - :exc:`InvalidID`
