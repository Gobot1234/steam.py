"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from ...enums import IntEnum


class EMsg(IntEnum):
    # EGCBaseClientMsg from source: gcsystemmsgs.proto

    GCPingRequest = 3001
    GCPingResponse = 3002
    GCToClientPollConvarRequest = 3003
    GCToClientPollConvarResponse = 3004
    GCCompressedMsgToClient = 3005
    GCCompressedMsgToClient_Legacy = 523
    GCToClientRequestDropped = 3006
    GCClientWelcome = 4004
    GCServerWelcome = 4005
    GCClientHello = 4006
    GCServerHello = 4007
    GCClientConnectionStatus = 4009
    GCServerConnectionStatus = 4010

    # EGCCitadelClientMessages from source: citadel_gcmessages_client.proto
    ClientToGCStartMatchmaking = 9010
    ClientToGCStartMatchmakingResponse = 9011
    ClientToGCStopMatchmaking = 9012
    ClientToGCStopMatchmakingResponse = 9013
    GCToClientMatchmakingStopped = 9014
    ClientToGCLeaveLobby = 9015
    ClientToGCLeaveLobbyResponse = 9016
    ClientToGCIsInMatchmaking = 9017
    ClientToGCIsInMatchmakingResponse = 9018
    GCToClientDevPlaytestStatus = 9019
    ClientToGCDevSetMMBias = 9023
    ClientToGCGetProfileCard = 9024
    ClientToGCGetProfileCardResponse = 9025
    ClientToGCUpdateRoster = 9026
    ClientToGCUpdateRosterResponse = 9027
    GCToClientProfileCardUpdated = 9028
    GCToClientDevAnnouncements = 9029
    ClientToGCModifyDevAnnouncements = 9030
    ClientToGCModifyDevAnnouncementsResponse = 9031
    GCToClientSDRTicket = 9100
    ClientToGCReplacementSDRTicket = 9101
    ClientToGCReplacementSDRTicketResponse = 9102
    ClientToGCSetServerConVar = 9107
    ClientToGCSetServerConVarResponse = 9108
    ClientToGCSpectateLobby = 9109
    ClientToGCSpectateLobbyResponse = 9110
    ClientToGCPostMatchSurveyResponse = 9111
    ClientToGCGetMatchHistory = 9112
    ClientToGCGetMatchHistoryResponse = 9113
    ClientToGCSpectateUser = 9116
    ClientToGCSpectateUserResponse = 9117
    ClientToGCPartyCreate = 9123
    ClientToGCPartyCreateResponse = 9124
    ClientToGCPartyLeave = 9125
    ClientToGCPartyLeaveResponse = 9126
    ClientToGCPartyJoin = 9127
    ClientToGCPartyJoinResponse = 9128
    ClientToGCPartyAction = 9129
    ClientToGCPartyActionResponse = 9130
    ClientToGCPartyStartMatch = 9131
    ClientToGCPartyStartMatchResponse = 9132
    ClientToGCPartyInviteUser = 9133
    ClientToGCPartyInviteUserResponse = 9134
    GCToClientPartyEvent = 9135
    GCToClientCanRejoinParty = 9137
    ClientToGCPartyJoinViaCode = 9138
    ClientToGCPartyJoinViaCodeResponse = 9139
    ClientToGCPartyUpdateRoster = 9140
    ClientToGCPartyUpdateRosterResponse = 9141
    ClientToGCPartySetReadyState = 9142
    ClientToGCPartySetReadyStateResponse = 9143
    ClientToGCGetAccountStats = 9164
    ClientToGCGetAccountStatsResponse = 9165
    GCToClientAccountStatsUpdated = 9166
    ClientToGCGetMatchMetaData = 9167
    ClientToGCGetMatchMetaDataResponse = 9168
    ClientToGCDevAction = 9172
    ClientToGCDevActionResponse = 9173
    ClientToGCRecordClientEvents = 9174
    ClientToGCRecordClientEventsResponse = 9175
    ClientToGCSetNewPlayerProgress = 9176
    ClientToGCSetNewPlayerProgressResponse = 9177
    ClientToGCUpdateAccountSync = 9178
    ClientToGCUpdateAccountSyncResponse = 9179
    ClientToGCGetHeroChoice = 9180
    ClientToGCGetHeroChoiceResponse = 9181
    ClientToGCUnlockHero = 9182
    ClientToGCUnlockHeroResponse = 9183
    ClientToGCBookUnlock = 9184
    ClientToGCBookUnlockResponse = 9185
    ClientToGCGetBook = 9186
    ClientToGCGetBookResponse = 9187
    GCToClientBookUpdated = 9188
    ClientToGCSubmitPlaytestUser = 9189
    ClientToGCSubmitPlaytestUserResponse = 9190
    ClientToGCUpdateHeroBuild = 9193
    ClientToGCUpdateHeroBuildResponse = 9194
    ClientToGCFindHeroBuilds = 9195
    ClientToGCFindHeroBuildsResponse = 9196
    ClientToGCReportPlayerFromMatch = 9197
    ClientToGCReportPlayerFromMatchResponse = 9198
    ClientToGCGetAccountMatchReports = 9199
    ClientToGCGetAccountMatchReportsResponse = 9200
    ClientToGCDeleteHeroBuild = 9201
    ClientToGCDeleteHeroBuildResponse = 9202
    ClientToGCGetActiveMatches = 9203
    ClientToGCGetActiveMatchesResponse = 9204
    ClientToGCGetDiscordLink = 9205
    ClientToGCGetDiscordLinkResponse = 9206
    ClientToGCPartySetMode = 9207
    ClientToGCPartySetModeResponse = 9208
    ClientToGCGrantForumAccess = 9209
    ClientToGCGrantForumAccessResponse = 9210
    ClientToGCModeratorRequest = 9211
    ClientToGCModeratorRequestResponse = 9212
    ClientToGCGetFriendGameStatus = 9213
    ClientToGCGetFriendGameStatusResponse = 9214
    ClientToGCUpdateHeroBuildPreference = 9215
    ClientToGCUpdateHeroBuildPreferenceResponse = 9216
    ClientToGCGetOldHeroBuildData = 9217
    ClientToGCGetOldHeroBuildDataResponse = 9218
    ClientToGCUpdateSpectatorStatus = 9219
