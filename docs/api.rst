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


.. autoclass:: Client
    :members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error,
                      on_message, on_typing,
                      on_trade, on_trade_update,
                      on_comment,
                      on_invite, on_invite_accept, on_invite_decline, on_friend_add, on_user_update,
                      on_friend_remove,
                      on_clan_join, on_clan_update,
                      on_clan_leave,
                      on_group_join, on_group_update, on_group_leave,
                      on_event_create, on_announcement_create,


.. _event-reference:

Event Reference
---------------

This page outlines the different types of events listened for by the :class:`Client`.

There are two ways to register an event, the first way is through the use of :meth:`Client.event`. The second way is
through subclassing :class:`Client` and overriding the specific events. For example:

.. code:: python3

    import steam


    class MyClient(steam.Client):
        async def on_trade(self, trade: steam.TradeOffer) -> None:
            if not trade.is_our_offer():
                await trade.user.send("Thank you for your trade")
                print(f"Received trade: #{trade.id}")
                print("Trade partner is:", trade.user)
                print("We would send:", len(trade.sending), "items")
                print("We would receive:", len(trade.receiving), "items")

                if trade.is_gift():
                    print("Accepting the trade as it is a gift")
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

.. automethod:: Client.on_trade

.. automethod:: Client.on_trade_update

.. automethod:: Client.on_comment

.. automethod:: Client.on_invite

.. automethod:: Client.on_invite_accept

.. automethod:: Client.on_invite_decline

.. automethod:: Client.on_friend_add

.. automethod:: Client.on_user_update

.. automethod:: Client.on_friend_remove

.. automethod:: Client.on_clan_join

.. automethod:: Client.on_clan_update

.. automethod:: Client.on_clan_leave

.. automethod:: Client.on_group_join

.. automethod:: Client.on_group_update

.. automethod:: Client.on_group_leave

.. automethod:: Client.on_event_create

.. automethod:: Client.on_announcement_create


Utilities
----------

steam.py provides some utility functions.

.. autofunction:: steam.utils.parse_id64

.. autofunction:: steam.utils.id64_from_url

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

.. autoclass:: Currency()
    :members:
    :undoc-members:

.. autoclass:: PurchaseResult()
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

.. autoclass:: ContentDescriptor()
    :members:
    :undoc-members:

.. autoclass:: UserNewsType()
    :members:
    :undoc-members:


Intents
---------------
Intents allow you to control what data you wish to request from Steam, they are useful for reducing the overhead of the
library and allow you to chose what features you wish to enable. The should be passed to the :class:`Client`
constructor.

.. autoclass:: Intents()
    :members:
    :undoc-members:


Guard
---------------

.. autofunction:: steam.guard.get_authentication_code

.. autofunction:: steam.guard.get_confirmation_code

.. autofunction:: steam.guard.get_device_id


Abstract Base Classes
-----------------------

An :term:`abstract base class` (also known as an ``abc``) is a class that models can inherit their behaviour from.


.. autoclass:: steam.abc.BaseUser()
    :members:
    :undoc-members:
    :inherited-members:


.. autoclass:: steam.abc.Channel()
    :members:
    :inherited-members:


.. autoclass:: steam.abc.Commentable()
    :members:
    :inherited-members:


.. autoclass:: steam.abc.Messageable()
    :members:

Steam Models
---------------

steam.py provides wrappers around common Steam API objects.
These are not meant to be constructed by the user instead you receive them from methods/events.

Achievements
~~~~~~~~~~~~~~~


.. autoclass:: AppStat()
    :members:
    :inherited-members:


.. autoclass:: UserAppStat()
    :members:
    :inherited-members:


.. autoclass:: AppAchievement()
    :members:
    :inherited-members:


.. autoclass:: AppStatAchievement()
    :members:
    :inherited-members:


.. autoclass:: UserAppAchievement()
    :members:
    :inherited-members:


.. autoclass:: AppStats()
    :members:
    :inherited-members:


.. autoclass:: UserAppStats()
    :members:
    :inherited-members:

Announcements
~~~~~~~~~~~~~~~


.. autoclass:: Announcement
    :members:
    :inherited-members:


Badge
~~~~~~~~~~~~~~~


.. autoclass:: AppBadge()
    :members:


.. autoclass:: UserBadge()
    :members:


.. autoclass:: UserBadges()
    :members:


.. autoclass:: FavouriteBadge()
    :members:

Ban
~~~~~~~~~~~~~~~


.. autoclass:: Ban()
    :members:


Bundle
~~~~~~~~~~~~~~~


.. autoclass:: Bundle()
    :members:


.. autoclass:: PartialBundle()
    :members:


.. autoclass:: FetchedBundle()
    :members:


Channel
~~~~~~~~~~~~~~~


.. autoclass:: UserChannel()
    :members:
    :inherited-members:


.. autoclass:: GroupChannel()
    :members:
    :inherited-members:


.. autoclass:: ClanChannel()
    :members:
    :inherited-members:


Clan
~~~~~~~~~~~~~~~


.. autoclass:: Clan()
    :members:
    :inherited-members:


Comment
~~~~~~~~~~~~~~~


.. autoclass:: Comment()
    :members:


Events
~~~~~~~~~~~~~~~


.. autoclass:: Event()
    :members:
    :inherited-members:


Game Servers
~~~~~~~~~~~~~~~


.. autoclass:: GameServer()
    :members:
    :inherited-members:


.. autoclass:: Query()
    :members:


Group
~~~~~~~~~~~~~~~


.. autoclass:: Group()
    :members:
    :inherited-members:

Invite
~~~~~~~~~~~~~~~


.. autoclass:: UserInvite()
    :members:
    :inherited-members:


.. autoclass:: ClanInvite()
    :members:
    :inherited-members:

Leaderboard
~~~~~~~~~~~~~~~


.. autoclass:: Leaderboard()
    :members:
    :inherited-members:


.. autoclass:: LeaderboardUser()
    :members:
    :undoc-members:
    :inherited-members:


.. autoclass:: LeaderboardScoreUpdate()
    :members:

Manifests
~~~~~~~~~~~~~~~


.. autoclass:: Manifest()
   :members:


.. autoclass:: ManifestPath()
   :members:
   :inherited-members:


.. autoclass:: Branch()
   :members:


.. autoclass:: ManifestInfo()
   :members:


.. autoclass:: HeadlessDepot()
   :members:


.. autoclass:: Depot()
   :members:
   :inherited-members:


.. autoclass:: AppInfo()
   :members:
   :inherited-members:


.. autoclass:: PackageInfo()
   :members:
   :inherited-members:

Message
~~~~~~~~~~~~~~~


.. autoclass:: Message()
    :members:


.. autoclass:: UserMessage()
    :members:
    :inherited-members:


.. autoclass:: GroupMessage()
    :members:
    :inherited-members:


.. autoclass:: ClanMessage()
    :members:
    :inherited-members:

Package
~~~~~~~~~~~~~~~


.. autoclass:: Package()
   :members:


.. autoclass:: steam.package.PartialPackage()
   :members:
   :inherited-members:


.. autoclass:: steam.FetchedPackage()
   :members:
   :inherited-members:


.. autoclass:: License()
   :members:
   :inherited-members:


.. autoclass:: FetchedAppPackage()
   :members:
   :inherited-members:


Post
~~~~~~~~~~~~~~~


.. autoclass:: Post()
    :members:
    :inherited-members:


PriceOverview
~~~~~~~~~~~~~~~


.. autoclass:: PriceOverview()
    :members:

Profile
~~~~~~~~~~~~~~~


.. autoclass:: ProfileInfo()
    :members:


.. autoclass:: ProfileItem()
    :members:


.. autoclass:: OwnedProfileItems()
    :members:


.. autoclass:: EquippedProfileItems()
    :members:


.. autoclass:: ProfileShowcase()
    :members:


.. autoclass:: Profile()
    :members:
    :inherited-members:


PublishedFile
~~~~~~~~~~~~~~~


.. autoclass:: PublishedFile()
    :members:
    :inherited-members:


Store
~~~~~~~~~~~~~~~


.. autoclass:: StoreItem()
    :members:
    :inherited-members:


.. autoclass:: AppStoreItem()
    :members:
    :inherited-members:


.. autoclass:: PackageStoreItem()
    :members:
    :inherited-members:


.. autoclass:: BundleStoreItem()
    :members:
    :inherited-members:


.. autoclass:: TransactionReceipt()
    :members:
    :inherited-members:

App Tickets
~~~~~~~~~~~~~~~


.. autoclass:: EncryptedTicket()
    :members:
    :inherited-members:
    :undoc-members:


.. autoclass:: OwnershipTicket()
    :members:
    :inherited-members:
    :undoc-members:


.. autoclass:: AuthenticationTicket()
    :members:
    :inherited-members:
    :undoc-members:


.. autoclass:: AuthenticationTicketVerificationResult()
    :members:
    :inherited-members:
    :undoc-members:

Trading
~~~~~~~~~~~~~~~


.. autoclass:: Inventory()
    :members:
    :inherited-members:


.. autoclass:: Item()
    :members:
    :inherited-members:


.. autoclass:: Asset()
    :members:


.. autoclass:: MovedItem()
    :members:

Reactions
~~~~~~~~~~~~~~~


.. autoclass:: Award()
    :members:
    :inherited-members:


.. autoclass:: AwardReaction()
    :members:
    :inherited-members:


.. autoclass:: PartialMessageReaction()
    :members:
    :inherited-members:


.. autoclass:: MessageReaction()
    :members:
    :inherited-members:


.. autoclass:: Emoticon()
    :members:
    :inherited-members:


.. autoclass:: Sticker()
    :members:
    :inherited-members:


.. autoclass:: ClientEmoticon()
    :members:
    :inherited-members:


.. autoclass:: ClientSticker()
    :members:
    :inherited-members:

.. attributetable:: ClientEffect

.. autoclass:: ClientEffect()
    :members:
    :inherited-members:


.. autoclass:: ClientEffect()
    :members:
    :inherited-members:

Reviews
~~~~~~~~~~~~~~~


.. autoclass:: Review()
    :members:
    :inherited-members:


.. autoclass:: ReviewUser()
    :members:
    :undoc-members:
    :inherited-members:

Roles
~~~~~~~~~~~~~~~


.. autoclass:: Role()
    :members:


.. autoclass:: RolePermissions()
    :members:

User News
~~~~~~~~~~~~~~~


.. autoclass:: UserNews
    :members:
    :undoc-members:

Users
~~~~~~~~~~~~~~~


.. autoclass:: PartialUser()
    :members:
    :undoc-members:
    :inherited-members:


.. autoclass:: ClientUser()
    :members:
    :undoc-members:
    :inherited-members:


.. autoclass:: User()
    :members:
    :undoc-members:
    :inherited-members:


.. autoclass:: Friend()
    :members:
    :undoc-members:
    :inherited-members:

Wallet
~~~~~~~~~~~~~~~


.. autoclass:: Wallet()


Data-Classes
---------------

There are a few classes that can be constructed by the user, these include.

App
~~~~~~~~~~~~~~~


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


.. autoclass:: OwnershipTicket()
    :inherited-members:
    :members:


.. autoclass:: AuthenticationTicket()
    :inherited-members:
    :members:


.. autoclass:: EncryptedTicket()
    :inherited-members:
    :members:


.. autoclass:: AppShopItem
    :inherited-members:
    :members:


.. autoclass:: AppShopItemTag
    :inherited-members:
    :members:


.. autoclass:: AppShopItems
    :inherited-members:
    :members:


.. autoclass:: CommunityItem
    :inherited-members:
    :members:


.. autoclass:: RewardItem
    :inherited-members:
    :members:



.. autoclass:: steam.app.PartialApp()
    :inherited-members:
    :members:


.. autoclass:: UserApp()
    :inherited-members:
    :members:


.. autoclass:: WishlistApp()
    :inherited-members:
    :members:


.. autoclass:: FetchedApp()
    :inherited-members:
    :members:


.. autoclass:: DLC()
    :inherited-members:
    :members:


Steam IDs
~~~~~~~~~~~~~~~


.. autoclass:: ID
    :members:

TradeOffers
~~~~~~~~~~~~~~~


.. autoclass:: TradeOffer
    :members:


Media
~~~~~~~~~~~~~~~


.. autoclass:: Media
    :members:

Exceptions
------------

The following exceptions are thrown by the library.

.. autoexception:: SteamException

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
