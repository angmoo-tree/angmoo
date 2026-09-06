"""Shared multi-domain test fixtures; not imported by product code."""

from types import SimpleNamespace
from app.runtime.persistence.model_registration import register_models
from app.domains.operations.models import AdminAuditLog
from app.domains.characters.models import AgentCreationDraft
from app.domains.routines.models.resident import AgentActivityLog
from app.domains.memory.models.daypart import AgentDaypartMemoryEvent
from app.domains.routines.models.resident import AgentFeedCue
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.domains.relationships.models.points import AgentRelationshipPoint
from app.domains.local_bot.models import AgentLocalKey
from app.domains.routines.models.resident import AgentActivitySetting
from app.domains.characters.models import AgentImageGenerationSetting
from app.domains.routines.models.resident import AgentRun
from app.domains.routines.models.resident import AgentSlot
from app.domains.identity.models import AuthSession
from app.domains.identity.models import AuthExternalVerificationReservation
from app.domains.identity.models import AuthGoogleSignupGrant
from app.domains.identity.models import AuthLoginThrottleBucket
from app.domains.identity.models import CommunityMutationQuotaBucket
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.models import LocalOwnerBootstrapChallenge
from app.domains.runtime.models import RuntimeSchedulerLease
from app.domains.characters.models import Character
from app.domains.chat.models import CharacterMessageSetting
from app.domains.chat.models import ChatResponseRequest
from app.domains.character_lore.models import CharacterLoreChunk
from app.domains.character_lore.models import CharacterLoreSource
from app.domains.character_lore.models import LoreParserLease
from app.domains.characters.models import CharacterState
from app.domains.social.models.posts import Comment
from app.domains.identity.models import LlmCredential
from app.domains.local_bot.models import LocalBotActionQuotaBucket
from app.domains.local_bot.models import LocalBotReadQuotaBucket
from app.domains.chat.models import MessageMessage
from app.domains.chat.models import MessageThread
from app.domains.memory.models.items import MemoryCandidate
from app.domains.memory.models.batch import MemoryActivationEpoch
from app.domains.memory.models.batch import MemoryBatchProfile
from app.domains.memory.models.batch import MemoryBatchRun
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.models.batch import MemorySelectionDecisionModel
from app.domains.memory.models.batch import MemorySourceDelivery
from app.domains.memory.models.items import MemoryHotBrief
from app.domains.memory.models.items import MemoryHotBriefItem
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.items import MemoryItemEvidence
from app.domains.memory.models.items import MemoryMaintenanceJob
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.social.models.posts import Notification
from app.domains.social.models.posts import Post
from app.domains.social.models.posts import PostImageGenerationJob
from app.domains.social.models.posts import PostImageQuotaReservation
from app.domains.social.models.posts import PostLike
from app.domains.social.models.posts import PostMedia
from app.domains.social.models.posts import PostReport
from app.domains.social.models.posts import PostRepost
from app.domains.social.models.posts import ProfileFollow
from app.domains.characters.models import ProfileImageCandidate
from app.domains.characters.models import ProfileImageQuotaReservation
from app.domains.operations.models import SiteOperationBanner
from app.domains.operations.models import SiteOperationSetting
from app.domains.tree.models import TreeComment
from app.domains.tree.models import TreePost
from app.domains.identity.models import User
from app.domains.chat.models import UserMessagePreference
from app.domains.world_characters.models import CharacterActiveWorld
from app.domains.worlds.models import World
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldDaypartProfile
from app.domains.worlds.models import WorldGlossaryTerm
from app.domains.worlds.models import WorldMembership
from app.domains.worlds.models import WorldPlace
from app.domains.worlds.models import WorldRole
from app.domains.worlds.models import WorldRule
from app.domains.world_characters.models import WorldActivityCandidate
from app.domains.world_characters.models import WorldActivityRepertoire
from app.domains.world_characters.models import WorldCharacterSetupAttempt
from app.domains.world_characters.models import WorldCommunityProfile
from app.domains.routines.models.plans import ActivityBeat
from app.domains.routines.models.plans import ActivityEpisode
from app.domains.routines.models.plans import ActivityEventConsumption
from app.domains.routines.models.plans import ActivityPlanRevision
from app.domains.routines.models.plans import DailyActivityPlan
from app.domains.routines.models.plans import DailyActivityPlanItem
from app.domains.routines.models.plans import JointActivity
from app.domains.routines.models.plans import JointActivityParticipant
from app.domains.routines.models.plans import JointActivityRepresentationClaim
from app.domains.social.models.feed import WorldCharacterBlock
from app.domains.social.models.feed import WorldCharacterFeedCursor
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.relationships.models.social import ActivityProposal
from app.domains.relationships.models.social import GraphProjectionOutbox
from app.domains.relationships.models.projection import GraphProjectionReplayRun
from app.domains.relationships.models.social import RelationshipState
from app.domains.relationships.models.social import RelationshipStateChange
from app.domains.relationships.models.social import SocialEvent
from app.domains.relationships.models.social import SocialEventEvidence
from app.domains.social.models.manual_writes import OwnerManualInboxCandidate
from app.domains.social.models.manual_writes import OwnerManualSocialWrite
from app.domains.social.models.subjective_context import SocialActionSubjectiveContext
from app.domains.world_packages.models import WorldPackageExport
from app.domains.world_packages.models import WorldPackageImport
from app.domains.world_packages.models import WorldPackageImportIdMap
from app.domains.world_packages.models import WorldPackageSource

register_models()

models = SimpleNamespace(
    AdminAuditLog=AdminAuditLog,
    AgentCreationDraft=AgentCreationDraft,
    AgentActivityLog=AgentActivityLog,
    AgentDaypartMemoryEvent=AgentDaypartMemoryEvent,
    AgentFeedCue=AgentFeedCue,
    AgentPublicActionExecution=AgentPublicActionExecution,
    AgentRelationshipPoint=AgentRelationshipPoint,
    AgentLocalKey=AgentLocalKey,
    AgentActivitySetting=AgentActivitySetting,
    AgentImageGenerationSetting=AgentImageGenerationSetting,
    AgentRun=AgentRun,
    AgentSlot=AgentSlot,
    AuthSession=AuthSession,
    AuthExternalVerificationReservation=AuthExternalVerificationReservation,
    AuthGoogleSignupGrant=AuthGoogleSignupGrant,
    AuthLoginThrottleBucket=AuthLoginThrottleBucket,
    CommunityMutationQuotaBucket=CommunityMutationQuotaBucket,
    InstallationIdentity=InstallationIdentity,
    LocalOwnerBootstrapChallenge=LocalOwnerBootstrapChallenge,
    RuntimeSchedulerLease=RuntimeSchedulerLease,
    Character=Character,
    CharacterMessageSetting=CharacterMessageSetting,
    ChatResponseRequest=ChatResponseRequest,
    CharacterLoreChunk=CharacterLoreChunk,
    CharacterLoreSource=CharacterLoreSource,
    LoreParserLease=LoreParserLease,
    CharacterState=CharacterState,
    Comment=Comment,
    LlmCredential=LlmCredential,
    LocalBotActionQuotaBucket=LocalBotActionQuotaBucket,
    LocalBotReadQuotaBucket=LocalBotReadQuotaBucket,
    MessageMessage=MessageMessage,
    MessageThread=MessageThread,
    MemoryCandidate=MemoryCandidate,
    MemoryActivationEpoch=MemoryActivationEpoch,
    MemoryBatchProfile=MemoryBatchProfile,
    MemoryBatchRun=MemoryBatchRun,
    MemoryBatchSetting=MemoryBatchSetting,
    MemorySelectionDecisionModel=MemorySelectionDecisionModel,
    MemorySourceDelivery=MemorySourceDelivery,
    MemoryHotBrief=MemoryHotBrief,
    MemoryHotBriefItem=MemoryHotBriefItem,
    MemoryItem=MemoryItem,
    MemoryItemEvidence=MemoryItemEvidence,
    MemoryMaintenanceJob=MemoryMaintenanceJob,
    MemoryScopeSettingModel=MemoryScopeSettingModel,
    Notification=Notification,
    Post=Post,
    PostImageGenerationJob=PostImageGenerationJob,
    PostImageQuotaReservation=PostImageQuotaReservation,
    PostLike=PostLike,
    PostMedia=PostMedia,
    PostReport=PostReport,
    PostRepost=PostRepost,
    ProfileFollow=ProfileFollow,
    ProfileImageCandidate=ProfileImageCandidate,
    ProfileImageQuotaReservation=ProfileImageQuotaReservation,
    SiteOperationBanner=SiteOperationBanner,
    SiteOperationSetting=SiteOperationSetting,
    TreeComment=TreeComment,
    TreePost=TreePost,
    User=User,
    UserMessagePreference=UserMessagePreference,
    CharacterActiveWorld=CharacterActiveWorld,
    World=World,
    WorldCharacter=WorldCharacter,
    WorldDaypartProfile=WorldDaypartProfile,
    WorldGlossaryTerm=WorldGlossaryTerm,
    WorldMembership=WorldMembership,
    WorldPlace=WorldPlace,
    WorldRole=WorldRole,
    WorldRule=WorldRule,
    WorldActivityCandidate=WorldActivityCandidate,
    WorldActivityRepertoire=WorldActivityRepertoire,
    WorldCharacterSetupAttempt=WorldCharacterSetupAttempt,
    WorldCommunityProfile=WorldCommunityProfile,
    ActivityBeat=ActivityBeat,
    ActivityEpisode=ActivityEpisode,
    ActivityEventConsumption=ActivityEventConsumption,
    ActivityPlanRevision=ActivityPlanRevision,
    DailyActivityPlan=DailyActivityPlan,
    DailyActivityPlanItem=DailyActivityPlanItem,
    JointActivity=JointActivity,
    JointActivityParticipant=JointActivityParticipant,
    JointActivityRepresentationClaim=JointActivityRepresentationClaim,
    WorldCharacterBlock=WorldCharacterBlock,
    WorldCharacterFeedCursor=WorldCharacterFeedCursor,
    WorldCharacterFeedObservation=WorldCharacterFeedObservation,
    ActivityProposal=ActivityProposal,
    GraphProjectionOutbox=GraphProjectionOutbox,
    GraphProjectionReplayRun=GraphProjectionReplayRun,
    RelationshipState=RelationshipState,
    RelationshipStateChange=RelationshipStateChange,
    SocialEvent=SocialEvent,
    SocialEventEvidence=SocialEventEvidence,
    OwnerManualInboxCandidate=OwnerManualInboxCandidate,
    OwnerManualSocialWrite=OwnerManualSocialWrite,
    SocialActionSubjectiveContext=SocialActionSubjectiveContext,
    WorldPackageExport=WorldPackageExport,
    WorldPackageImport=WorldPackageImport,
    WorldPackageImportIdMap=WorldPackageImportIdMap,
    WorldPackageSource=WorldPackageSource,
)
