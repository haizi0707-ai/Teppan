import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="鉄板⭐️血統アプリ", layout="wide")

st.title("鉄板⭐️血統アプリ")
st.caption("GitHubに置くCSVはロジック辞書とコース判定の2つだけです。予想CSVは画面内に貼り付けます。種牡馬/母父名から系統を自動補完できます。")

# 取得できない場合がある項目。
# 列が無い/空欄の場合は、その条件だけスキップ扱いにします。
OPTIONAL_NEUTRAL_ITEMS = {"天気", "馬場状態", "前走調教師", "前走所属"}

TARGET_HEADERLESS_COLUMNS = [
    "日付", "競馬場", "R", "レース名", "芝ダ", "距離", "馬番", "馬名",
    "種牡馬", "父タイプ名", "母父名", "母父タイプ名",
    "性別", "年齢", "斤量", "頭数",
    "前走馬場状態", "前芝・ダ", "前距離", "前走斤量", "休み明け〜戦目",
    "所属", "調教師", "騎手", "前走騎手", "前走着順", "前走着差"
]


def looks_like_target_headerless(df):
    """
    TARGETの出力でヘッダーなしの場合、pandasが1行目を列名にしてしまう。
    例: 0509,新潟,新1,障害未勝利,芝,2890,...
    これを検出する。
    """
    cols = [str(c).strip() for c in df.columns]
    if len(cols) < 8:
        return False

    date_like = bool(re.fullmatch(r"\d{3,8}", cols[0]))
    place_like = cols[1] in ["札", "函", "福", "新", "東", "中", "名", "京", "阪", "小",
                             "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]
    r_like = bool(re.search(r"\d+", cols[2]))
    surface_like = cols[4] in ["芝", "ダ", "障", "芝ダ"] or bool(re.search(r"[芝ダ]\d+", cols[4]))
    distance_like = bool(re.search(r"\d+", cols[5]))

    return date_like and place_like and r_like and surface_like and distance_like




# =========================
# 読み込み・正規化
# =========================
def read_csv_smart(path_or_buf):
    encodings = ["utf-8-sig", "utf-8", "cp932", "shift_jis"]
    last_err = None
    for enc in encodings:
        try:
            if isinstance(path_or_buf, (str, Path)):
                df = pd.read_csv(path_or_buf, encoding=enc)
                if looks_like_target_headerless(df):
                    raw = pd.read_csv(path_or_buf, encoding=enc, header=None)
                    raw = raw.iloc[:, :len(TARGET_HEADERLESS_COLUMNS)]
                    raw.columns = TARGET_HEADERLESS_COLUMNS[:len(raw.columns)]
                    return raw
                return df

            path_or_buf.seek(0)
            df = pd.read_csv(path_or_buf, encoding=enc)
            if looks_like_target_headerless(df):
                path_or_buf.seek(0)
                raw = pd.read_csv(path_or_buf, encoding=enc, header=None)
                raw = raw.iloc[:, :len(TARGET_HEADERLESS_COLUMNS)]
                raw.columns = TARGET_HEADERLESS_COLUMNS[:len(raw.columns)]
                return raw
            return df

        except Exception as e:
            last_err = e
    raise last_err


def norm_text(v):
    if pd.isna(v):
        return ""
    s = str(v).strip()
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", "", s)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def to_float_safe(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s == "":
        return None
    # TARGETの着差は「0.5」「-0.1」「1 1/4」など混在する可能性があるため、まず数値だけ拾う
    s = s.replace("秒", "").replace("+", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def to_int_safe(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s == "":
        return None
    m = re.search(r"\d+", s)
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def teppan_rank(row):
    """
    鉄板⭐️：血統ロジック該当
    強鉄板⭐️：前走5着以内 または 前走着差0.5秒以内
    超鉄板⭐️：前走5着以内 かつ 前走着差0.5秒以内
    """
    prev_rank = to_int_safe(row.get("前走着順", ""))
    prev_margin = to_float_safe(row.get("前走着差", ""))

    rank_ok = prev_rank is not None and prev_rank <= 5
    margin_ok = prev_margin is not None and prev_margin <= 0.5

    if rank_ok and margin_ok:
        return "超鉄板⭐️"
    if rank_ok or margin_ok:
        return "強鉄板⭐️"
    return "鉄板⭐️"


def teppan_reason(row):
    prev_rank = row.get("前走着順", "")
    prev_margin = row.get("前走着差", "")
    pr = to_int_safe(prev_rank)
    pm = to_float_safe(prev_margin)
    parts = []
    if pr is not None:
        parts.append(f"前走着順={pr}着")
    if pm is not None:
        parts.append(f"前走着差={pm:.1f}秒")
    if not parts:
        return "血統ロジック該当"
    return " / ".join(parts)


def norm_col(c):
    s = str(c).strip()
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", "", s)
    s = s.replace("芝・ダ", "芝ダ")
    s = s.replace("芝ダート", "芝ダ")
    s = s.replace("～", "〜")
    s = s.replace("Ｒ", "R")
    return s


def normalize_df(df):
    df = df.copy()
    df.columns = [norm_col(c) for c in df.columns]

    rename_map = {
        "場所": "競馬場",
        "場": "競馬場",
        "レース番号": "R",
        "馬番号": "馬番",
        "父系統": "父タイプ名",
        "母父系統": "母父タイプ名",
        "前芝ダ": "前芝・ダ",
        "前走芝ダ": "前芝・ダ",
        "前走芝・ダ": "前芝・ダ",
        "前走距離": "前距離",
        "前走馬場": "前走馬場状態",
        "前走馬場状態名": "前走馬場状態",
        "馬場": "馬場状態",
        "休み明け～戦目": "休み明け〜戦目",
        "休明け〜戦目": "休み明け〜戦目",
        "休明け～戦目": "休み明け〜戦目",
        "父名": "種牡馬",
        "父馬名": "種牡馬",
        "父": "種牡馬",
        "母父": "母父名",
        "母父馬名": "母父名",
        "前騎手": "前走騎手",
        "前着順": "前走着順",
        "前走着": "前走着順",
        "前走着差": "前走着差",
        "前差": "前走着差",
    }

    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    # 性齢 → 性別・年齢
    if "性齢" in df.columns:
        if "性別" not in df.columns:
            df["性別"] = df["性齢"].astype(str).str.extract(r"([牡牝セ騙])", expand=False).fillna("")
        if "年齢" not in df.columns:
            df["年齢"] = df["性齢"].astype(str).str.extract(r"(\d+)", expand=False).fillna("")

    # 所属がない場合、調教師欄の先頭(美)/(栗)などから作る
    if "所属" not in df.columns and "調教師" in df.columns:
        df["所属"] = df["調教師"].astype(str).str.extract(r"(\([美栗地外]\)|美|栗|地|外)", expand=False).fillna("")

    # 前走所属がない場合は所属で代替
    if "前走所属" not in df.columns and "所属" in df.columns:
        df["前走所属"] = df["所属"]

    # 替がない場合、騎手と前走騎手から作る
    if "替" not in df.columns:
        if "騎手" in df.columns and "前走騎手" in df.columns:
            now_j = df["騎手"].map(norm_text)
            prev_j = df["前走騎手"].map(norm_text)
            df["替"] = ["*" if n and p and n != p else "" for n, p in zip(now_j, prev_j)]
        else:
            df["替"] = ""

    # TARGETで「場」が1文字略称の場合に正式名へ変換
    if "競馬場" in df.columns:
        place_map = {
            "札": "札幌", "函": "函館", "福": "福島", "新": "新潟", "東": "東京",
            "中": "中山", "名": "中京", "京": "京都", "阪": "阪神", "小": "小倉",
            "札幌": "札幌", "函館": "函館", "福島": "福島", "新潟": "新潟", "東京": "東京",
            "中山": "中山", "中京": "中京", "京都": "京都", "阪神": "阪神", "小倉": "小倉",
        }
        df["競馬場"] = df["競馬場"].apply(lambda x: place_map.get(norm_text(x), norm_text(x)))

    # TARGETで距離列が「芝2890」「ダ1800」のように芝ダ込みの場合、
    # 芝ダ列と数値距離列へ自動分解する
    if "距離" in df.columns:
        dist_s = df["距離"].astype(str)
        if "芝ダ" not in df.columns:
            df["芝ダ"] = dist_s.str.extract(r"([芝ダ])", expand=False).fillna("")
        else:
            df["芝ダ"] = df["芝ダ"].apply(norm_text)
            missing_surface = df["芝ダ"].eq("")
            extracted_surface = dist_s.str.extract(r"([芝ダ])", expand=False).fillna("")
            df.loc[missing_surface, "芝ダ"] = extracted_surface[missing_surface]
        df["距離"] = dist_s.str.extract(r"(\d+)", expand=False).fillna(df["距離"].astype(str))

    # Rが「7R」でも「7」でも照合できるように数値へ寄せる
    if "R" in df.columns:
        df["R"] = df["R"].astype(str).str.extract(r"(\d+)", expand=False).fillna(df["R"].astype(str))

    return df


def csv_files():
    return sorted(Path(".").glob("*.csv"), key=lambda p: p.name)


# =========================
# ロジックCSVの自動検出
# =========================
def detect_files():
    logic_path = None
    course_path = None

    for f in csv_files():
        try:
            df = normalize_df(read_csv_smart(f))
            cols = set(df.columns)

            is_logic = (
                {"競馬場", "距離", "芝ダ"}.issubset(cols)
                and (
                    "最終対象系統" in cols
                    or "対象系統" in cols
                    or "条件1項目" in cols
                    or "条件1内容" in cols
                )
            )

            is_course = (
                {"競馬場", "距離", "芝ダ"}.issubset(cols)
                and "判定" in cols
                and (
                    "リフト" in cols
                    or "複勝率%" in cols
                    or "複勝回収率%" in cols
                    or "該当頭数" in cols
                )
            )

            if is_logic and ("最終対象系統" in cols or "条件1項目" in cols):
                logic_path = f
            elif is_course:
                course_path = f
            elif is_logic and logic_path is None:
                logic_path = f

        except Exception:
            pass

    return logic_path, course_path


# =========================
# 種牡馬/母父名 → 系統補完
# =========================
def build_bloodline_type_map(logic_df):
    """
    ロジック辞書だけでは個別種牡馬名までは入っていないため、
    基本は手動辞書＋任意の変換CSVを使う。
    変換CSVが同じフォルダにある場合は優先的に読み込む。
    """
    base = {
        # ロイヤルチャージャー系
        "ディープインパクト": "ロイヤルチャージャー系",
        "キズナ": "ロイヤルチャージャー系",
        "シルバーステート": "ロイヤルチャージャー系",
        "リアルスティール": "ロイヤルチャージャー系",
        "サトノダイヤモンド": "ロイヤルチャージャー系",
        "エピファネイア": "ロイヤルチャージャー系",
        "モーリス": "ロイヤルチャージャー系",
        "ハーツクライ": "ロイヤルチャージャー系",
        "ジャスタウェイ": "ロイヤルチャージャー系",
        "ダイワメジャー": "ロイヤルチャージャー系",
        "ゴールドシップ": "ロイヤルチャージャー系",
        "ステイゴールド": "ロイヤルチャージャー系",
        "オルフェーヴル": "ロイヤルチャージャー系",
        "ドリームジャーニー": "ロイヤルチャージャー系",
        "スクリーンヒーロー": "ロイヤルチャージャー系",
        "リオンディーズ": "ロイヤルチャージャー系",
        "ニューイヤーズデイ": "ロイヤルチャージャー系",
        "ブリックスアンドモルタル": "ロイヤルチャージャー系",
        "スワーヴリチャード": "ロイヤルチャージャー系",
        "レイデオロ": "ロイヤルチャージャー系",
        "イスラボニータ": "ロイヤルチャージャー系",
        "サトノクラウン": "ロイヤルチャージャー系",
        "ミッキーアイル": "ロイヤルチャージャー系",
        "ルーラーシップ": "ネイティヴダンサー系",
        "ロードカナロア": "ネイティヴダンサー系",
        "ドゥラメンテ": "ネイティヴダンサー系",
        "キングカメハメハ": "ネイティヴダンサー系",
        "ホッコータルマエ": "ネイティヴダンサー系",
        "カリフォルニアクローム": "ネイティヴダンサー系",
        "パイロ": "ネイティヴダンサー系",
        "アドマイヤムーン": "ネイティヴダンサー系",
        "アルアイン": "ネイティヴダンサー系",
        "レッドファルクス": "ネイティヴダンサー系",
        "サンダースノー": "ネイティヴダンサー系",
        # ニアークティック系
        "ヘニーヒューズ": "ニアークティック系",
        "ドレフォン": "ニアークティック系",
        "キタサンブラック": "ニアークティック系",
        "ブラックタイド": "ニアークティック系",
        "ダンカーク": "ニアークティック系",
        "マクフィ": "ニアークティック系",
        "マインドユアビスケッツ": "ニアークティック系",
        "アジアエクスプレス": "ニアークティック系",
        "ディスクリートキャット": "ニアークティック系",
        "シニスターミニスター": "ニアークティック系",
        "デクラレーションオブウォー": "ニアークティック系",
        "ミスターメロディ": "ニアークティック系",
        "アメリカンペイトリオット": "ニアークティック系",
        "ノヴェリスト": "ニアークティック系",
        "ファインニードル": "ニアークティック系",
        "タワーオブロンドン": "ニアークティック系",
        # ナスルーラ系
        "サクラバクシンオー": "ナスルーラ系",
        "ビッグアーサー": "ナスルーラ系",
        "トーセンラー": "ナスルーラ系",
        "エイシンフラッシュ": "ナスルーラ系",
        "ベストウォーリア": "ナスルーラ系",
        "ヨハネスブルグ": "ナスルーラ系",
        "ジャングルポケット": "ナスルーラ系",
        "バゴ": "ナスルーラ系",
        "トーセンジョーダン": "ナスルーラ系",
        # その他
        "サウスヴィグラス": "ナスルーラ系",
        "コパノリッキー": "ナスルーラ系",
        "フリオーソ": "ロベルト系",
        "マジェスティックウォリアー": "ナスルーラ系",
        "アニマルキングダム": "ネイティヴダンサー系",
        "ゴールドアリュール": "ロイヤルチャージャー系",
        "スマートファルコン": "ロイヤルチャージャー系",
        "トビーズコーナー": "ナスルーラ系",

        # ユーザー追加：未変換だった種牡馬/母父名 v3
        "AdiosCharlie": "ネイティヴダンサー系",
        "Charlatan": "ネイティヴダンサー系",
        "StudyofMan": "ネイティヴダンサー系",
        "TwirlingCandy": "ネイティヴダンサー系",
        "WoottonBassett": "ニアークティック系",
        "アポロケンタッキー": "ネイティヴダンサー系",
        "インディチャンプ": "ロイヤルチャージャー系",
        "オウケンワールド": "ロイヤルチャージャー系",
        "サトノジェネシス": "ロイヤルチャージャー系",
        "ショウナンバッハ": "ロイヤルチャージャー系",
        "ミスチヴィアスアレックス": "ニアークティック系",
        "ミッキースワロー": "ロイヤルチャージャー系",
        "Alamosa": "ニアークティック系",
        "Anodin": "ネイティヴダンサー系",
        "Astrology": "ナスルーラ系",
        "BatedBreath": "ニアークティック系",
        "Bodemeister": "ネイティヴダンサー系",
        "CrockerRoad": "ネイティヴダンサー系",
        "DaiwaMajor": "ロイヤルチャージャー系",
        "EqualStripes": "ナスルーラ系",
        "Haynesfield": "ネイティヴダンサー系",
        "Liaison": "ナスルーラ系",
        "LordKanaloa": "ネイティヴダンサー系",
        "MagnaGraduate": "ネイティヴダンサー系",
        "NeedsFurther": "ニアークティック系",
        "PointofEntry": "ロイヤルチャージャー系",
        "RipVanWinkle": "ニアークティック系",
        "SeattleFitz": "ナスルーラ系",
        "SoYouThink": "ニアークティック系",
        "StormEmbrujado": "ニアークティック系",
        "SwissSpirit": "ニアークティック系",
        "Uncaptured": "ネイティヴダンサー系",
        "VictoirePisa": "ロイヤルチャージャー系",
        "Wilburn": "ナスルーラ系",
        "ハードスパン": "ニアークティック系",
        "モンテロッソ": "ネイティヴダンサー系",

        # ユーザー追加：未変換だった種牡馬/母父名
        "AmericanPharoah": "ネイティヴダンサー系",
        "ArmyMule": "ネイティヴダンサー系",
        "Authentic": "ネイティヴダンサー系",
        "Caravaggio": "ニアークティック系",
        "CityofLight": "ネイティヴダンサー系",
        "Collected": "ネイティヴダンサー系",
        "Constitution": "ナスルーラ系",
        "DandyMan": "ニアークティック系",
        "Exceedance": "ニアークティック系",
        "Farhh": "ネイティヴダンサー系",
        "Frosted": "ネイティヴダンサー系",
        "GlobalCampaign": "ナスルーラ系",
        "GoldenHorn": "ニアークティック系",
        "GoodMagic": "ナスルーラ系",
        "GunRunner": "ネイティヴダンサー系",
        "HarryAngel": "ニアークティック系",
        "IntoMischief": "ニアークティック系",
        "Justify": "ネイティヴダンサー系",
        "Kingman": "ニアークティック系",
        "Klimt": "ナスルーラ系",
        "Leinster": "ネイティヴダンサー系",
        "Liam'sMap": "ナスルーラ系",
        "Maclean'sMusic": "ネイティヴダンサー系",
        "Masar": "ネイティヴダンサー系",
        "McKinzie": "ネイティヴダンサー系",
        "Mitole": "ネイティヴダンサー系",
        "MorSpirit": "ネイティヴダンサー系",
        "Nathaniel": "ニアークティック系",
        "NightofThunder": "ネイティヴダンサー系",
        "NoNayNever": "ニアークティック系",
        "Nyquist": "ナスルーラ系",
        "OmahaBeach": "ネイティヴダンサー系",
        "OscarPerformance": "ニアークティック系",
        "PracticalJoke": "ナスルーラ系",
        "Preservationist": "ネイティヴダンサー系",
        "Runhappy": "ネイティヴダンサー系",
        "SaxonWarrior": "ロイヤルチャージャー系",
        "StMark'sBasilica": "ニアークティック系",
        "TakeChargeIndy": "ナスルーラ系",
        "TiztheLaw": "ナスルーラ系",
        "TooDarnHot": "ニアークティック系",
        "UnionRags": "ニアークティック系",
        "VinoRosso": "ナスルーラ系",
        "Zoustar": "ニアークティック系",
        "アイファーソング": "ロイヤルチャージャー系",
        "アドマイヤマーズ": "ロイヤルチャージャー系",
        "アドミラブル": "ロイヤルチャージャー系",
        "アルバート": "ロイヤルチャージャー系",
        "アレスバローズ": "ロイヤルチャージャー系",
        "ウインブライト": "ロイヤルチャージャー系",
        "ウォータービルド": "ロイヤルチャージャー系",
        "エイシンヒカリ": "ロイヤルチャージャー系",
        "エスケンデレヤ": "ネイティヴダンサー系",
        "エスポワールシチー": "ロイヤルチャージャー系",
        "エタリオウ": "ロイヤルチャージャー系",
        "エピカリス": "ロイヤルチャージャー系",
        "オーヴァルエース": "ロイヤルチャージャー系",
        "カレンブラックヒル": "ロイヤルチャージャー系",
        "キセキ": "ネイティヴダンサー系",
        "クリエイター2": "ナスルーラ系",
        "クリソベリル": "ロイヤルチャージャー系",
        "クレスコグランド": "ロイヤルチャージャー系",
        "グァンチャーレ": "ロイヤルチャージャー系",
        "グランデッツァ": "ロイヤルチャージャー系",
        "グランプリボス": "ナスルーラ系",
        "グレーターロンドン": "ロイヤルチャージャー系",
        "ケープブランコ": "ニアークティック系",
        "コントレイル": "ロイヤルチャージャー系",
        "ゴールデンバローズ": "ナスルーラ系",
        "ゴールデンマンデラ": "ニアークティック系",
        "ゴールドアクター": "ロイヤルチャージャー系",
        "ゴールドドリーム": "ロイヤルチャージャー系",
        "サトノアラジン": "ロイヤルチャージャー系",
        "サートゥルナーリア": "ネイティヴダンサー系",
        "ザファクター": "ネイティヴダンサー系",
        "シゲルカガ": "ナスルーラ系",
        "シスキン": "ニアークティック系",
        "シビルウォー": "ネイティヴダンサー系",
        "シャンハイボビー": "ナスルーラ系",
        "シュヴァルグラン": "ロイヤルチャージャー系",
        "ストロングリターン": "ロイヤルチャージャー系",
        "スピルバーグ": "ロイヤルチャージャー系",
        "スマートオーディン": "ロイヤルチャージャー系",
        "タニノフランケル": "ニアークティック系",
        "タリスマニック": "ネイティヴダンサー系",
        "ダノンキングリー": "ロイヤルチャージャー系",
        "ダノンスマッシュ": "ネイティヴダンサー系",
        "ダノンバラード": "ロイヤルチャージャー系",
        "ダノンプレミアム": "ロイヤルチャージャー系",
        "ダノンレジェンド": "ネイティヴダンサー系",
        "ディーマジェスティ": "ロイヤルチャージャー系",
        "トゥザグローリー": "ネイティヴダンサー系",
        "トゥザワールド": "ネイティヴダンサー系",
        "トーセンレーヴ": "ロイヤルチャージャー系",
        "トーホウジャッカル": "ロイヤルチャージャー系",
        "ドリームバレンチノ": "ロイヤルチャージャー系",
        "ナダル": "ニアークティック系",
        "ニシケンモノノフ": "ナスルーラ系",
        "ネロ": "ナスルーラ系",
        "ノーブルミッション": "ニアークティック系",
        "ハクサンムーン": "ネイティヴダンサー系",
        "ハッピースプリント": "ナスルーラ系",
        "バンドワゴン": "ニアークティック系",
        "パドトロワ": "ロイヤルチャージャー系",
        "ビーチパトロール": "ネイティヴダンサー系",
        "フィエールマン": "ロイヤルチャージャー系",
        "フィレンツェファイア": "ナスルーラ系",
        "フェノーメノ": "ロイヤルチャージャー系",
        "フォーウィールドライブ": "ネイティヴダンサー系",
        "ヘンリーバローズ": "ロイヤルチャージャー系",
        "ベルシャザール": "ネイティヴダンサー系",
        "ベンバトル": "ネイティヴダンサー系",
        "ホークビル": "ニアークティック系",
        "ポアゾンブラック": "ネイティヴダンサー系",
        "ポエティックフレア": "ニアークティック系",
        "マテラスカイ": "ナスルーラ系",
        "マルターズアポジー": "ニアークティック系",
        "ミッキーグローリー": "ロイヤルチャージャー系",
        "ミッキーロケット": "ネイティヴダンサー系",
        "ミュゼスルタン": "ネイティヴダンサー系",
        "モズアスコット": "ニアークティック系",
        "モーニン": "ニアークティック系",
        "ヤマカツエース": "ネイティヴダンサー系",
        "ヤングマンパワー": "ニアークティック系",
        "ユアーズトゥルーリ": "ネイティヴダンサー系",
        "ラニ": "ナスルーラ系",
        "ラブリーデイ": "ネイティヴダンサー系",
        "リアルインパクト": "ロイヤルチャージャー系",
        "リオンリオン": "ネイティヴダンサー系",
        "ルヴァンスレーヴ": "ロイヤルチャージャー系",
        "レインボーライン": "ロイヤルチャージャー系",
        "レオアクティブ": "ロイヤルチャージャー系",
        "レッドベルジュール": "ロイヤルチャージャー系",
        "レーヴミストラル": "ネイティヴダンサー系",
        "ロゴタイプ": "ロイヤルチャージャー系",
        "ロジャーバローズ": "ロイヤルチャージャー系",
        "ロジユニヴァース": "ニアークティック系",
        "ワンアンドオンリー": "ロイヤルチャージャー系",
        "ワールドエース": "ロイヤルチャージャー系",
        "ワールドプレミア": "ロイヤルチャージャー系",
        "ヴァンキッシュラン": "ロイヤルチャージャー系",
        "ヴァンゴッホ": "ニアークティック系",
        "ヴァンセンヌ": "ロイヤルチャージャー系",
    }

    # 任意変換CSVを読み込み
    # 例: 血統タイプ変換表.csv / bloodline_type_map.csv
    for f in csv_files():
        name = f.name
        if not any(key in name for key in ["血統タイプ変換", "種牡馬タイプ変換", "bloodline_type"]):
            continue
        try:
            mdf = normalize_df(read_csv_smart(f))
            cols = set(mdf.columns)
            horse_col = None
            type_col = None
            for c in ["種牡馬", "種牡馬名", "父名", "母父名", "血統名"]:
                if c in cols:
                    horse_col = c
                    break
            for c in ["タイプ名", "父タイプ名", "母父タイプ名", "系統", "血統系統"]:
                if c in cols:
                    type_col = c
                    break
            if horse_col and type_col:
                for _, r in mdf.iterrows():
                    k = norm_text(r.get(horse_col, ""))
                    v = norm_text(r.get(type_col, ""))
                    if k and v:
                        base[k] = v
        except Exception:
            pass

    return {norm_text(k): norm_text(v) for k, v in base.items()}


def fill_bloodline_types(input_df, type_map):
    df = input_df.copy()

    if "父タイプ名" not in df.columns:
        df["父タイプ名"] = ""
    if "母父タイプ名" not in df.columns:
        df["母父タイプ名"] = ""

    # 種牡馬 → 父タイプ名
    if "種牡馬" in df.columns:
        for i, r in df.iterrows():
            if not norm_text(r.get("父タイプ名", "")):
                sire = norm_text(r.get("種牡馬", ""))
                if sire in type_map:
                    df.at[i, "父タイプ名"] = type_map[sire]

    # 母父名 → 母父タイプ名
    if "母父名" in df.columns:
        for i, r in df.iterrows():
            if not norm_text(r.get("母父タイプ名", "")):
                damsire = norm_text(r.get("母父名", ""))
                if damsire in type_map:
                    df.at[i, "母父タイプ名"] = type_map[damsire]

    return df


# =========================
# ロジック照合
# =========================
def get_condition_pairs(rule, max_n=12):
    pairs = []
    for i in range(1, max_n + 1):
        item = norm_text(rule.get(f"条件{i}項目", ""))
        content = norm_text(rule.get(f"条件{i}内容", ""))
        if item and content:
            pairs.append((item, content))
    return pairs


def match_value(row, item, expected):
    item = norm_text(item)
    expected = norm_text(expected)

    if not item or not expected:
        return True

    item_map = {
        "芝・ダ": "芝ダ",
        "前芝ダ": "前芝・ダ",
        "前走芝ダ": "前芝・ダ",
        "前走芝・ダ": "前芝・ダ",
        "休み明け～戦目": "休み明け〜戦目",
    }
    lookup = item_map.get(item, item)

    if lookup == "前走所属" and lookup not in row.index and "所属" in row.index:
        lookup = "所属"

    if lookup not in row.index:
        if item in OPTIONAL_NEUTRAL_ITEMS or lookup in OPTIONAL_NEUTRAL_ITEMS:
            return True
        return False

    actual = norm_text(row.get(lookup, ""))

    if actual == "":
        if item in OPTIONAL_NEUTRAL_ITEMS or lookup in OPTIONAL_NEUTRAL_ITEMS:
            return True
        return False

    if lookup == "替" and expected == "*":
        return actual != ""

    return actual == expected


def target_systems_list(rule):
    raw = ""
    for c in ["最終対象系統", "対象系統", "残留系統", "項目8残留系統"]:
        if c in rule.index and norm_text(rule.get(c, "")):
            raw = str(rule.get(c, ""))
            break

    if not raw:
        return []

    parts = re.split(r"[、,/／・\s]+", raw)
    return [norm_text(p) for p in parts if norm_text(p)]



def apply_manual_conditions(input_df, default_weather="", default_going="", override_text=""):
    """
    画面で入力した天気・馬場状態を、予想CSVに補完する。
    override_text はCSV形式:
    競馬場,芝ダ,天気,馬場状態
    東京,芝,晴,良
    東京,ダ,晴,稍重
    """
    df = normalize_df(input_df)

    default_weather = norm_text(default_weather)
    default_going = norm_text(default_going)

    if "天気" not in df.columns:
        df["天気"] = ""
    if "馬場状態" not in df.columns:
        df["馬場状態"] = ""

    if default_weather:
        df["天気"] = df["天気"].apply(lambda x: default_weather if norm_text(x) == "" else x)
    if default_going:
        df["馬場状態"] = df["馬場状態"].apply(lambda x: default_going if norm_text(x) == "" else x)

    if override_text and str(override_text).strip():
        try:
            ov = read_csv_smart(io.StringIO(override_text))
            ov = normalize_df(ov)

            for c in ["競馬場", "芝ダ", "天気", "馬場状態"]:
                if c not in ov.columns:
                    ov[c] = ""

            for _, r in ov.iterrows():
                place = norm_text(r.get("競馬場", ""))
                surface = norm_text(r.get("芝ダ", ""))
                weather = norm_text(r.get("天気", ""))
                going = norm_text(r.get("馬場状態", ""))

                mask = pd.Series([True] * len(df), index=df.index)

                if place:
                    if "競馬場" in df.columns:
                        mask &= df["競馬場"].map(norm_text).eq(place)
                    else:
                        mask &= False

                if surface:
                    if "芝ダ" in df.columns:
                        mask &= df["芝ダ"].map(norm_text).eq(surface)
                    else:
                        mask &= False

                if weather:
                    df.loc[mask, "天気"] = weather
                if going:
                    df.loc[mask, "馬場状態"] = going

        except Exception:
            # 補完CSVの形式が崩れていても、アプリ全体は止めない
            pass

    return df


def build_result(input_df, logic_df, course_df, use_statuses):
    input_df = normalize_df(input_df)
    logic_df = normalize_df(logic_df)
    course_df = normalize_df(course_df)

    type_map = build_bloodline_type_map(logic_df)
    input_df = fill_bloodline_types(input_df, type_map)

    required = ["競馬場", "芝ダ", "距離", "馬名"]
    missing = [c for c in required if c not in input_df.columns]
    if missing:
        raise ValueError("入力CSVに不足列があります: " + ", ".join(missing) + "\n現在読み込めた列: " + ", ".join(map(str, input_df.columns)))

    if "父タイプ名" not in input_df.columns and "種牡馬" not in input_df.columns:
        raise ValueError("父タイプ名または種牡馬のどちらかが必要です。")
    if "母父タイプ名" not in input_df.columns and "母父名" not in input_df.columns:
        raise ValueError("母父タイプ名または母父名のどちらかが必要です。")

    for df in [input_df, logic_df, course_df]:
        for c in ["競馬場", "芝ダ", "距離"]:
            if c in df.columns:
                df[c] = df[c].map(norm_text)

    use_statuses_norm = [norm_text(x) for x in use_statuses]
    course_use = course_df[course_df["判定"].astype(str).map(norm_text).isin(use_statuses_norm)].copy()

    results = []
    unknown_sires = set()
    unknown_damsires = set()

    for _, h in input_df.iterrows():
        if not norm_text(h.get("父タイプ名", "")) and norm_text(h.get("種牡馬", "")):
            unknown_sires.add(norm_text(h.get("種牡馬", "")))
        if not norm_text(h.get("母父タイプ名", "")) and norm_text(h.get("母父名", "")):
            unknown_damsires.add(norm_text(h.get("母父名", "")))

        course_key = (
            norm_text(h.get("競馬場", "")),
            norm_text(h.get("芝ダ", "")),
            norm_text(h.get("距離", "")),
        )

        course_match = course_use[
            (course_use["競馬場"].map(norm_text) == course_key[0])
            & (course_use["芝ダ"].map(norm_text) == course_key[1])
            & (course_use["距離"].map(norm_text) == course_key[2])
        ]
        if course_match.empty:
            continue

        logic_match = logic_df[
            (logic_df["競馬場"].map(norm_text) == course_key[0])
            & (logic_df["芝ダ"].map(norm_text) == course_key[1])
            & (logic_df["距離"].map(norm_text) == course_key[2])
        ]
        if logic_match.empty:
            continue

        course_row = course_match.iloc[0]

        for _, rule in logic_match.iterrows():
            blood_type = norm_text(rule.get("血統区分", ""))
            systems = target_systems_list(rule)
            father_sys = norm_text(h.get("父タイプ名", ""))
            mb_sys = norm_text(h.get("母父タイプ名", ""))

            hit_system = ""
            hit_blood_type = blood_type

            if blood_type == "父系":
                if father_sys in systems:
                    hit_system = father_sys
            elif blood_type == "母父系":
                if mb_sys in systems:
                    hit_system = mb_sys
            else:
                if father_sys in systems:
                    hit_system = father_sys
                    hit_blood_type = "父系"
                elif mb_sys in systems:
                    hit_system = mb_sys
                    hit_blood_type = "母父系"

            if not hit_system:
                continue

            conds = get_condition_pairs(rule)
            ok_conds = []
            ng_conds = []
            for item, content in conds:
                if match_value(h, item, content):
                    ok_conds.append(f"{item}={content}")
                else:
                    ng_conds.append(f"{item}={content}")

            if ng_conds:
                continue

            results.append({
                "判定": str(course_row.get("判定", "")),
                "優先度": str(course_row.get("優先度", "")),
                "日付": str(h.get("日付", "")),
                "競馬場": course_key[0],
                "R": str(h.get("R", "")),
                "レース名": str(h.get("レース名", "")),
                "芝ダ": course_key[1],
                "距離": course_key[2],
                "馬番": str(h.get("馬番", "")),
                "馬名": str(h.get("馬名", "")),
                "種牡馬": str(h.get("種牡馬", "")),
                "母父名": str(h.get("母父名", "")),
                "父タイプ名": father_sys,
                "母父タイプ名": mb_sys,
                "血統区分": hit_blood_type,
                "該当系統": hit_system,
                "鉄板ランク": teppan_rank(h),
                "鉄板ランク理由": teppan_reason(h),
                "前走着順": str(h.get("前走着順", "")),
                "前走着差": str(h.get("前走着差", "")),
                "一致条件数": len(ok_conds),
                "一致条件": " / ".join(ok_conds),
                "検証複勝率%": str(course_row.get("複勝率%", "")),
                "複勝回収率%": str(course_row.get("複勝回収率%", "")),
                "リフト": str(course_row.get("リフト", "")),
                "該当頭数_検証": str(course_row.get("該当頭数", "")),
                "判定理由": str(course_row.get("判定理由", "")),
            })

    out = pd.DataFrame(results)
    if not out.empty:
        rank_order = {"超鉄板⭐️": 0, "強鉄板⭐️": 1, "鉄板⭐️": 2}
        out["_rank_order"] = out["鉄板ランク"].map(rank_order).fillna(9)
        sort_cols = [c for c in ["_rank_order", "判定", "優先度", "競馬場", "R", "馬番"] if c in out.columns]
        out = out.sort_values(sort_cols).drop(columns=["_rank_order"]).reset_index(drop=True)

    return out, sorted(unknown_sires), sorted(unknown_damsires)


# =========================
# 画面
# =========================
logic_path, course_path = detect_files()

with st.sidebar:
    st.header("設定")
    use_statuses = st.multiselect(
        "使用するコース判定",
        ["採用", "保留", "除外"],
        default=["採用"],
        help="基本は採用のみ。候補を広げたい場合だけ保留を追加してください。",
    )
    show_debug = st.checkbox("CSV検出状況を表示", value=True)

if show_debug:
    st.subheader("CSV検出状況")
    st.write("現在このフォルダで見えているCSV:")
    files = [f.name for f in csv_files()]
    st.code("\n".join(files) if files else "CSVファイルが見つかりません")

    st.write("自動判定結果:")
    st.code(
        f"ロジック辞書: {logic_path.name if logic_path else '未検出'}\n"
        f"コース判定: {course_path.name if course_path else '未検出'}"
    )

if logic_path is None or course_path is None:
    st.error("必要なCSVを自動判定できませんでした。")
    st.write("必要なCSVは app.py と同じ場所に置いてください。")
    st.code("① ロジック辞書CSV：最終対象系統・条件1項目などが入っているCSV\n② コース判定CSV：判定・リフト・複勝率%などが入っているCSV")
    st.stop()

try:
    logic_df = normalize_df(read_csv_smart(logic_path))
    course_df = normalize_df(read_csv_smart(course_path))
except Exception as e:
    st.error("ロジックCSVまたはコース判定CSVの読み込みに失敗しました。")
    st.exception(e)
    st.stop()

st.success("ロジックCSVとコース判定CSVを読み込みました。")
st.caption(f"ロジック辞書: {logic_path.name}")
st.caption(f"コース判定: {course_path.name}")

st.subheader("予想CSV貼り付け")
st.info("予想CSVはGitHubに置かず、画面内で貼り付けるか、CSVファイルを読み込んでください。父タイプ名が空欄でも、種牡馬があれば一部自動補完します。")

with st.expander("TARGETから抜く推奨列を見る", expanded=True):
    st.code(
        """ヘッダーありの場合:
日付,場,R,レース名,芝ダ,距離,馬番,馬名,種牡馬,父タイプ名,母父名,母父タイプ名,性別,年齢,斤量,頭数,前走馬場状態,前芝・ダ,前距離,前走斤量,休み明け～戦目,所属,調教師,騎手,前騎手,前走着順,前走着差

ヘッダーなしTARGET出力もそのまま読み込めます。""",
        language="csv",
    )
    st.caption("父タイプ名が空欄でも種牡馬から補完します。前走着順・前走着差から、鉄板⭐️/強鉄板⭐️/超鉄板⭐️を自動判定します。性齢・Ｒ・休み明け～戦目などの表記ゆれも吸収します。結果は詳細版と、複合アプリ用の8列版の両方を出力できます。")

st.subheader("予想CSVの入力")
st.caption("ファイル読み込み・CSV貼り付けのどちらでも使えます。両方ある場合はファイル読み込みを優先します。")

uploaded_file = st.file_uploader(
    "予想CSVファイルを選択",
    type=["csv"],
    key="prediction_upload",
    help="TARGETから出力したCSVをそのまま読み込めます。Shift_JIS / CP932 / UTF-8 に対応しています。",
)
st.caption("iPhoneの場合は、ファイルアプリに保存したCSVを選択してください。")

with st.expander("CSVを貼り付ける場合", expanded=False):
    csv_text = st.text_area(
        "予想に必要な項目CSVをここに貼り付け",
        height=260,
        placeholder="日付,場所,R,レース名,芝・ダ,距離,馬番,馬名,種牡馬,父タイプ名,母父名,母父タイプ名,...",
    )

st.subheader("天気・馬場状態の選択補完")
st.caption("TARGETから天気・馬場状態が取れない場合だけ使います。競馬場ごとに芝・ダを選んで、天気と馬場状態を指定できます。")

manual_weather = ""
manual_going = ""
manual_rows = []

with st.expander("競馬場・芝ダごとに指定する", expanded=True):
    st.caption("最大3会場×芝/ダの6枠まで同時指定できます。芝とダで馬場状態が違う場合も分けて指定できます。TARGETのヘッダーなしCSV、列が「場」、Rが「新1」、距離が「芝2890/ダ1800」でも自動変換します。")

    racecourse_options = ["", "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]
    weather_options = ["", "晴", "曇", "雨", "小雨", "雪"]
    going_options = ["", "良", "稍重", "重", "不良"]

    for i in range(1, 4):
        st.markdown(f"**会場{i}**")

        place = st.selectbox(
            f"競馬場{i}",
            racecourse_options,
            index=0,
            key=f"manual_place_{i}",
        )

        st.caption("芝")
        c1, c2 = st.columns(2)
        with c1:
            turf_weather = st.selectbox(
                f"芝 天気{i}",
                weather_options,
                index=0,
                key=f"manual_turf_weather_{i}",
            )
        with c2:
            turf_going = st.selectbox(
                f"芝 馬場状態{i}",
                going_options,
                index=0,
                key=f"manual_turf_going_{i}",
            )

        st.caption("ダ")
        c3, c4 = st.columns(2)
        with c3:
            dirt_weather = st.selectbox(
                f"ダ 天気{i}",
                weather_options,
                index=0,
                key=f"manual_dirt_weather_{i}",
            )
        with c4:
            dirt_going = st.selectbox(
                f"ダ 馬場状態{i}",
                going_options,
                index=0,
                key=f"manual_dirt_going_{i}",
            )

        if place:
            if turf_weather or turf_going:
                manual_rows.append({
                    "競馬場": place,
                    "芝ダ": "芝",
                    "天気": turf_weather,
                    "馬場状態": turf_going,
                })
            if dirt_weather or dirt_going:
                manual_rows.append({
                    "競馬場": place,
                    "芝ダ": "ダ",
                    "天気": dirt_weather,
                    "馬場状態": dirt_going,
                })

if manual_rows:
    manual_condition_csv = pd.DataFrame(manual_rows).to_csv(index=False)
else:
    manual_condition_csv = ""

with st.expander("補完内容を確認", expanded=False):
    if manual_condition_csv:
        st.code(manual_condition_csv, language="csv")
    else:
        st.caption("補完指定はありません。天気・馬場状態条件は空欄ならスキップされます。")

run = st.button("鉄板⭐️候補を抽出", type="primary", use_container_width=True)

if run:
    try:
        file_obj = uploaded_file
        if file_obj is None:
            file_obj = st.session_state.get("prediction_upload", None)

        if file_obj is not None:
            input_df = read_csv_smart(file_obj)
        elif csv_text.strip():
            input_df = read_csv_smart(io.StringIO(csv_text))
        else:
            st.warning("CSVファイルを選択するか、CSV本文を貼り付けてください。")
            st.stop()

        input_df = apply_manual_conditions(input_df, manual_weather, manual_going, manual_condition_csv)
        result, unknown_sires, unknown_damsires = build_result(input_df, logic_df, course_df, use_statuses)

        if unknown_sires or unknown_damsires:
            with st.expander("系統に変換できなかった種牡馬/母父を見る", expanded=False):
                if unknown_sires:
                    st.write("未変換の種牡馬")
                    st.code("\n".join(unknown_sires[:200]))
                if unknown_damsires:
                    st.write("未変換の母父")
                    st.code("\n".join(unknown_damsires[:200]))
                st.caption("必要なら、app.pyと同じ場所に 血統タイプ変換表.csv を置くと補完できます。列は 種牡馬名,タイプ名 などでOKです。")

        if result.empty:
            st.warning("該当馬はありませんでした。採用のみで出ない場合は、設定で保留も含めて確認してください。")
        else:
            st.success(f"該当馬 {len(result)}件を抽出しました。")

            if "鉄板ランク" in result.columns:
                st.subheader("鉄板ランク内訳")
                rank_counts = result["鉄板ランク"].value_counts().reindex(["超鉄板⭐️", "強鉄板⭐️", "鉄板⭐️"]).fillna(0).astype(int)
                st.dataframe(rank_counts.rename("頭数").reset_index().rename(columns={"index": "鉄板ランク"}), use_container_width=True, hide_index=True)

            st.dataframe(result, use_container_width=True, hide_index=True)

            csv_out = result.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "結果CSVをダウンロード（詳細版）",
                csv_out,
                file_name="teppan_bloodline_result.csv",
                mime="text/csv",
                use_container_width=True,
            )

            simple_cols = ["日付", "競馬場", "R", "レース名", "馬番", "馬名", "鉄板ランク", "判定"]
            simple_df = result.copy()
            for c in simple_cols:
                if c not in simple_df.columns:
                    simple_df[c] = ""
            simple_df = simple_df[simple_cols].copy()
            simple_csv = simple_df.to_csv(index=False, encoding="utf-8-sig")

            st.download_button(
                "結果CSVをダウンロード（複合アプリ用）",
                simple_csv,
                file_name="teppan_bloodline_result_for_composite.csv",
                mime="text/csv",
                use_container_width=True,
            )

            with st.expander("コピー用CSV（詳細版）", expanded=False):
                st.code(csv_out, language="csv")

            with st.expander("コピー用CSV（複合アプリ用）", expanded=False):
                st.code(simple_csv, language="csv")

    except Exception as e:
        st.error("処理中にエラーが出ました。")
        st.exception(e)
