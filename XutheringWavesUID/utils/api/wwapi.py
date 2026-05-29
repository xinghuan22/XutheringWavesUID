from typing import Dict, List, Literal, Optional

from pydantic import Field, BaseModel

MAIN_URL = "https://wh.loping151.site"
# MAIN_URL = "http://127.0.0.1:9001"

UPLOAD_URL = f"{MAIN_URL}/top/waves/upload"
GET_RANK_URL = f"{MAIN_URL}/top/waves/rank"
GET_TOTAL_RANK_URL = f"{MAIN_URL}/top/waves/total/rank"
ONE_RANK_URL = f"{MAIN_URL}/top/waves/one"
UPLOAD_ABYSS_RECORD_URL = f"{MAIN_URL}/top/waves/abyss/upload"
GET_ABYSS_RECORD_URL = f"{MAIN_URL}/top/waves/abyss/record"
GET_HOLD_RATE_URL = f"{MAIN_URL}/api/waves/hold/rates"
GET_POOL_LIST = f"{MAIN_URL}/api/waves/pool/list"
GET_TOWER_APPEAR_RATE = f"{MAIN_URL}/api/waves/abyss/appear_rate"
UPLOAD_SLASH_RECORD_URL = f"{MAIN_URL}/top/waves/slash/upload"
GET_SLASH_APPEAR_RATE = f"{MAIN_URL}/api/waves/slash/appear_rate"
GET_SLASH_RANK_URL = f"{MAIN_URL}/top/waves/slash/rank"
UPLOAD_MATRIX_RECORD_URL = f"{MAIN_URL}/top/waves/matrix/upload"
GET_MATRIX_RANK_URL = f"{MAIN_URL}/top/waves/matrix/rank"
GET_MATRIX_APPEAR_RATE = f"{MAIN_URL}/api/waves/matrix/appear_rate"
GET_CODE_URL = f"{MAIN_URL}/top/waves/code"

ABYSS_TYPE = Literal["l4", "m4", "r4", "a"]

ABYSS_TYPE_MAP = {
    "残响之塔": "l",
    "深境之塔": "m",
    "回音之塔": "r",
}

ABYSS_TYPE_MAP_REVERSE = {
    "l4": "残响之塔 - 4层",
    "m4": "深境之塔 - 4层",
    "r4": "回音之塔 - 4层",
}


class RankDetail(BaseModel):
    rank: int
    inter_rank: str
    user_id: str
    username: str
    alias_name: str
    kuro_name: str
    waves_id: str
    char_id: int
    level: int
    chain: int
    weapon_id: int
    weapon_level: int
    weapon_reson_level: int
    sonata_name: str
    phantom_score: float
    phantom_score_bg: str
    expected_damage: float
    expected_name: str
    sender_avatar: Optional[str] = ""


class RankInfoData(BaseModel):
    details: List[RankDetail]
    page: int
    page_num: int


class RankInfoResponse(BaseModel):
    code: int
    message: str
    data: Optional[RankInfoData] = None


class RankItem(BaseModel):
    char_id: int
    page: int
    page_num: int
    rank_type: int
    waves_id: Optional[str] = ""
    version: str


# ------------------------------------------------------------
# 总排行


class TotalRankRequest(BaseModel):
    page: int = Field(..., description="页码")
    page_num: int = Field(..., description="每页数量")
    version: str = Field(..., description="版本号")
    waves_id: str = Field(..., description="鸣潮id")


class CharScoreDetail(BaseModel):
    char_id: int
    phantom_score: float


class TotalRankDetail(BaseModel):
    rank: int
    user_id: str
    username: str
    alias_name: str
    kuro_name: str
    waves_id: str
    total_score: float
    char_score_details: List[CharScoreDetail]
    sender_avatar: Optional[str] = ""


class TotalRankInfoData(BaseModel):
    score_details: List[TotalRankDetail]
    page: int
    page_num: int


class TotalRankResponse(BaseModel):
    code: int
    message: str
    data: Optional[TotalRankInfoData] = None


# ------------------------------------------------------------


class OneRankRequest(BaseModel):
    char_id: int = Field(..., description="角色ID")
    waves_id: Optional[str] = Field(default="", description="鸣潮ID")
    phantom_score: Optional[float] = Field(default=None, description="声骸评分")
    expected_damage: Optional[float] = Field(default=None, description="期望伤害")


class OneRankResponse(BaseModel):
    code: int
    message: str
    data: List[RankDetail]


# ------------------------------------------------------------
# 深渊记录
# ------------------------------------------------------------


class AbyssDetail(BaseModel):
    area_type: ABYSS_TYPE
    area_name: str
    floor: int
    char_ids: List[int]


class AbyssItem(BaseModel):
    waves_id: str
    abyss_record: List[AbyssDetail]
    version: str


class AbyssRecordRequest(BaseModel):
    abyss_type: ABYSS_TYPE


class AbyssUseRate(BaseModel):
    char_id: int
    rate: float


class AbyssRecord(BaseModel):
    abyss_type: ABYSS_TYPE
    use_rate: List[AbyssUseRate]


class AbyssRecordResponse(BaseModel):
    code: int
    message: str
    data: List[AbyssRecord]


# ------------------------------------------------------------
# 角色持有率


class RoleHoldRate(BaseModel):
    char_id: int
    rate: float
    chain_rate: Dict[int, float]


class RoleHoldRateRequest(BaseModel):
    char_id: Optional[int] = None


class RoleHoldRateResponse(BaseModel):
    code: int
    message: str
    data: List[RoleHoldRate]


# ------------------------------------------------------------
# 冥海记录
# ------------------------------------------------------------


class SlashDetail(BaseModel):
    buffIcon: str
    buffName: str
    buffQuality: int
    charIds: List[int]
    score: int


class SlashDetailRequest(BaseModel):
    wavesId: str
    challengeId: int
    challengeName: str
    halfList: List[SlashDetail]
    rank: str
    score: int
    sender_avatar: Optional[str] = ""


# ------------------------------------------------------------
# 冥海排行
#
# ------------------------------------------------------------


class SlashRankItem(BaseModel):
    page: int
    page_num: int
    waves_id: str
    version: str


class SlashCharDetail(BaseModel):
    char_id: int  # 角色id
    level: int  # 角色等级
    chain: int  # 角色链


class SlashHalfList(BaseModel):
    buff_icon: str  # buff图标
    buff_name: str  # buff名称
    buff_quality: int  # buff品质
    char_detail: List[SlashCharDetail]  # 角色详细数据
    score: int  # 每层分数


class SlashRank(BaseModel):
    half_list: List[SlashHalfList]
    score: int  # 冥海总分数
    rank: int  # 总排名
    user_id: str  # 用户id
    waves_id: str  # 鸣潮id
    kuro_name: str  # 库洛用户名
    alias_name: str  # 主人别名
    sender_avatar: Optional[str] = ""


class SlashRankData(BaseModel):
    page: int  # 页码
    page_num: int  # 每页数量
    start_date: str  # 开始日期
    rank_list: List[SlashRank]  # 排行数据


class SlashRankRes(BaseModel):
    code: int
    message: str
    data: Optional[SlashRankData] = None


# ------------------------------------------------------------
# 矩阵记录
# ------------------------------------------------------------


class MatrixTeamDetail(BaseModel):
    buff_icon: str  # buff图标
    buff_name: str  # buff名称
    buff_id: int  # buffID
    role_icons: List[str]  # 角色头像URL列表
    char_ids: List[int] = Field(default_factory=list)  # 匹配出的角色ID列表
    score: int  # 队伍得分


class MatrixDetailRequest(BaseModel):
    wavesId: str
    modeId: int  # 模式ID (1=矩阵叠兵, 0=囚笼)
    rank: int  # 排名
    score: int  # 总分数
    teamCount: int = 0  # 使用队伍数
    teams: List[MatrixTeamDetail]  # 队伍列表
    sender_avatar: Optional[str] = ""


# ------------------------------------------------------------
# 矩阵排行
# ------------------------------------------------------------


class MatrixRankItem(BaseModel):
    page: int
    page_num: int
    waves_id: str
    version: str


class MatrixCharDetail(BaseModel):
    char_id: int
    level: int = -1
    chain: int = -1


class MatrixRankTeam(BaseModel):
    buff_icon: str
    buff_name: str
    role_icons: List[str] = Field(default_factory=list)
    char_detail: List[MatrixCharDetail] = Field(default_factory=list)
    score: int


class MatrixRank(BaseModel):
    teams: List[MatrixRankTeam]
    score: int  # 矩阵总分数
    rank: int  # 总排名
    team_count: int = 0  # 使用队伍数
    user_id: str
    waves_id: str
    kuro_name: str
    alias_name: str
    sender_avatar: Optional[str] = ""


class MatrixRankData(BaseModel):
    page: int
    page_num: int
    start_date: str
    rank_list: List[MatrixRank]


class MatrixRankRes(BaseModel):
    code: int
    message: str
    data: Optional[MatrixRankData] = None
