import io
import re
import base64
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None

st.set_page_config(page_title="鉄板⭐️血統アプリ", layout="wide")

st.title("鉄板⭐️血統アプリ")
st.caption("GitHubに置くCSVはロジック辞書とコース判定の2つだけです。予想CSVは画面内に貼り付けます。種牡馬/母父名から系統を自動補完できます。最終出力画像も作成できます。")

OPTIONAL_NEUTRAL_ITEMS = {"天気", "馬場状態", "前走調教師", "前走所属"}

TARGET_HEADERLESS_COLUMNS = [
    "日付", "競馬場", "R", "レース名", "芝ダ", "距離", "馬番", "馬名",
    "種牡馬", "父タイプ名", "母父名", "母父タイプ名",
    "性別", "年齢", "斤量", "頭数",
    "前走馬場状態", "前芝・ダ", "前距離", "前走斤量", "休み明け〜戦目",
    "所属", "調教師", "騎手", "前走騎手", "前走着順", "前走着差"
]

# =========================
# 読み込み・正規化
# =========================
def looks_like_target_headerless(df):
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
    s = str(v).strip().replace("\u3000", " ")
    s = re.sub(r"\s+", "", s)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def norm_col(c):
    s = str(c).strip().replace("\u3000", " ")
    s = re.sub(r"\s+", "", s)
    s = s.replace("芝・ダ", "芝ダ")
    s = s.replace("芝ダート", "芝ダ")
    s = s.replace("～", "〜")
    s = s.replace("Ｒ", "R")
    return s


def to_float_safe(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s == "":
        return None
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


def r_num(v):
    try:
        m = re.search(r"\d+", str(v))
        return int(m.group(0)) if m else None
    except Exception:
        return None


def normalize_df(df):
    df = df.copy()
    df.columns = [norm_col(c) for c in df.columns]

    rename_map = {
        "場所": "競馬場", "場": "競馬場", "レース番号": "R", "馬番号": "馬番",
        "父系統": "父タイプ名", "母父系統": "母父タイプ名",
        "前芝ダ": "前芝・ダ", "前走芝ダ": "前芝・ダ", "前走芝・ダ": "前芝・ダ",
        "前走距離": "前距離", "前走馬場": "前走馬場状態", "前走馬場状態名": "前走馬場状態",
        "馬場": "馬場状態", "休み明け～戦目": "休み明け〜戦目", "休明け〜戦目": "休み明け〜戦目",
        "休明け～戦目": "休み明け〜戦目", "父名": "種牡馬", "父馬名": "種牡馬", "父": "種牡馬",
        "母父": "母父名", "母父馬名": "母父名", "前騎手": "前走騎手",
        "前着順": "前走着順", "前走着": "前走着順", "前差": "前走着差",
        "種牡馬名": "種牡馬", "タイプ名": "父タイプ名",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    if "性齢" in df.columns:
        if "性別" not in df.columns:
            df["性別"] = df["性齢"].astype(str).str.extract(r"([牡牝セ騙])", expand=False).fillna("")
        if "年齢" not in df.columns:
            df["年齢"] = df["性齢"].astype(str).str.extract(r"(\d+)", expand=False).fillna("")

    if "所属" not in df.columns and "調教師" in df.columns:
        df["所属"] = df["調教師"].astype(str).str.extract(r"(\([美栗地外]\)|美|栗|地|外)", expand=False).fillna("")
    if "前走所属" not in df.columns and "所属" in df.columns:
        df["前走所属"] = df["所属"]

    if "替" not in df.columns:
        if "騎手" in df.columns and "前走騎手" in df.columns:
            now_j = df["騎手"].map(norm_text)
            prev_j = df["前走騎手"].map(norm_text)
            df["替"] = ["*" if n and p and n != p else "" for n, p in zip(now_j, prev_j)]
        else:
            df["替"] = ""

    if "競馬場" in df.columns:
        place_map = {"札": "札幌", "函": "函館", "福": "福島", "新": "新潟", "東": "東京", "中": "中山",
                     "名": "中京", "京": "京都", "阪": "阪神", "小": "小倉"}
        df["競馬場"] = df["競馬場"].apply(lambda x: place_map.get(norm_text(x), norm_text(x)))

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
                and ("最終対象系統" in cols or "対象系統" in cols or "条件1項目" in cols or "条件1内容" in cols)
            )
            is_course = (
                {"競馬場", "距離", "芝ダ"}.issubset(cols)
                and "判定" in cols
                and ("リフト" in cols or "複勝率%" in cols or "複勝回収率%" in cols or "該当頭数" in cols)
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
# 血統タイプ補完
# =========================
def build_bloodline_type_map(logic_df=None):
    # 最低限の固定辞書。足りないものは「血統タイプ変換表.csv」で補完できます。
    base = {
        "ディープインパクト": "ロイヤルチャージャー系", "キズナ": "ロイヤルチャージャー系",
        "エピファネイア": "ロイヤルチャージャー系", "ハーツクライ": "ロイヤルチャージャー系",
        "モーリス": "ロイヤルチャージャー系", "ダイワメジャー": "ロイヤルチャージャー系",
        "シルバーステート": "ロイヤルチャージャー系", "リアルスティール": "ロイヤルチャージャー系",
        "オルフェーヴル": "ロイヤルチャージャー系", "ゴールドシップ": "ロイヤルチャージャー系",
        "ルーラーシップ": "ネイティヴダンサー系", "ロードカナロア": "ネイティヴダンサー系",
        "ドゥラメンテ": "ネイティヴダンサー系", "キングカメハメハ": "ネイティヴダンサー系",
        "ホッコータルマエ": "ネイティヴダンサー系", "パイロ": "ネイティヴダンサー系",
        "ヘニーヒューズ": "ニアークティック系", "ドレフォン": "ニアークティック系",
        "キタサンブラック": "ニアークティック系", "ブラックタイド": "ニアークティック系",
        "マクフィ": "ニアークティック系", "シニスターミニスター": "ニアークティック系",
        "ビッグアーサー": "ナスルーラ系", "サクラバクシンオー": "ナスルーラ系",
        "バゴ": "ナスルーラ系", "コパノリッキー": "ナスルーラ系",
        "フリオーソ": "ロベルト系", "ゴールドアリュール": "ロイヤルチャージャー系",
    }

    loaded_map_files = []
    st.session_state["bloodline_type_map_loaded_files"] = loaded_map_files

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
                cnt = 0
                for _, r in mdf.iterrows():
                    k = norm_text(r.get(horse_col, ""))
                    v = norm_text(r.get(type_col, ""))
                    if k and v:
                        base[k] = v
                        cnt += 1
                loaded_map_files.append({"ファイル名": f.name, "馬名列": horse_col, "タイプ列": type_col, "読込件数": cnt})
            else:
                loaded_map_files.append({"ファイル名": f.name, "馬名列": horse_col or "未検出", "タイプ列": type_col or "未検出", "読込件数": 0})
        except Exception as e:
            loaded_map_files.append({"ファイル名": f.name, "馬名列": "", "タイプ列": "", "読込件数": 0, "エラー": str(e)})

    return {norm_text(k): norm_text(v) for k, v in base.items()}


def diagnose_bloodline_conversion_files():
    rows = []
    for f in csv_files():
        name = f.name
        if not any(key in name for key in ["血統タイプ変換", "種牡馬タイプ変換", "bloodline_type"]):
            continue
        info = {"ファイル名": name, "候補判定": "候補", "読込": "", "馬名列": "", "タイプ列": "", "変換件数": 0, "列名": "", "エラー": ""}
        try:
            mdf = normalize_df(read_csv_smart(f))
            cols = list(mdf.columns)
            info["列名"] = " / ".join(map(str, cols))
            horse_col = next((c for c in ["種牡馬", "種牡馬名", "父名", "母父名", "血統名"] if c in cols), None)
            type_col = next((c for c in ["タイプ名", "父タイプ名", "母父タイプ名", "系統", "血統系統"] if c in cols), None)
            info["馬名列"] = horse_col or "未検出"
            info["タイプ列"] = type_col or "未検出"
            if horse_col and type_col:
                valid = mdf[[horse_col, type_col]].dropna()
                valid = valid[(valid[horse_col].map(norm_text) != "") & (valid[type_col].map(norm_text) != "")]
                info["変換件数"] = len(valid)
                info["読込"] = "OK"
            else:
                info["読込"] = "列名不足"
        except Exception as e:
            info["読込"] = "NG"
            info["エラー"] = str(e)
        rows.append(info)
    return pd.DataFrame(rows)


def fill_bloodline_types(input_df, type_map):
    df = input_df.copy()
    if "父タイプ名" not in df.columns:
        df["父タイプ名"] = ""
    if "母父タイプ名" not in df.columns:
        df["母父タイプ名"] = ""
    if "種牡馬" in df.columns:
        for i, r in df.iterrows():
            if not norm_text(r.get("父タイプ名", "")):
                sire = norm_text(r.get("種牡馬", ""))
                if sire in type_map:
                    df.at[i, "父タイプ名"] = type_map[sire]
    if "母父名" in df.columns:
        for i, r in df.iterrows():
            if not norm_text(r.get("母父タイプ名", "")):
                damsire = norm_text(r.get("母父名", ""))
                if damsire in type_map:
                    df.at[i, "母父タイプ名"] = type_map[damsire]
    return df


# =========================
# 鉄板判定・照合
# =========================
def teppan_rank(row):
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
    pr = to_int_safe(row.get("前走着順", ""))
    pm = to_float_safe(row.get("前走着差", ""))
    parts = []
    if pr is not None:
        parts.append(f"前走着順={pr}着")
    if pm is not None:
        parts.append(f"前走着差={pm:.1f}秒")
    return " / ".join(parts) if parts else "血統ロジック該当"


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
    item_map = {"芝・ダ": "芝ダ", "前芝ダ": "前芝・ダ", "前走芝ダ": "前芝・ダ", "前走芝・ダ": "前芝・ダ", "休み明け～戦目": "休み明け〜戦目"}
    lookup = item_map.get(item, item)
    if lookup == "前走所属" and lookup not in row.index and "所属" in row.index:
        lookup = "所属"
    if lookup not in row.index:
        return True if item in OPTIONAL_NEUTRAL_ITEMS or lookup in OPTIONAL_NEUTRAL_ITEMS else False
    actual = norm_text(row.get(lookup, ""))
    if actual == "":
        return True if item in OPTIONAL_NEUTRAL_ITEMS or lookup in OPTIONAL_NEUTRAL_ITEMS else False
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
            ov = normalize_df(read_csv_smart(io.StringIO(override_text)))
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
                    mask &= df["競馬場"].map(norm_text).eq(place) if "競馬場" in df.columns else False
                if surface:
                    mask &= df["芝ダ"].map(norm_text).eq(surface) if "芝ダ" in df.columns else False
                if weather:
                    df.loc[mask, "天気"] = weather
                if going:
                    df.loc[mask, "馬場状態"] = going
        except Exception:
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

        course_key = (norm_text(h.get("競馬場", "")), norm_text(h.get("芝ダ", "")), norm_text(h.get("距離", "")))
        course_match = course_use[(course_use["競馬場"].map(norm_text) == course_key[0]) &
                                  (course_use["芝ダ"].map(norm_text) == course_key[1]) &
                                  (course_use["距離"].map(norm_text) == course_key[2])]
        if course_match.empty:
            continue
        logic_match = logic_df[(logic_df["競馬場"].map(norm_text) == course_key[0]) &
                               (logic_df["芝ダ"].map(norm_text) == course_key[1]) &
                               (logic_df["距離"].map(norm_text) == course_key[2])]
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

            ok_conds, ng_conds = [], []
            for item, content in get_condition_pairs(rule):
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
        out["_Rnum"] = out["R"].map(r_num).fillna(999)
        out["_馬番"] = out["馬番"].map(r_num).fillna(999)
        sort_cols = [c for c in ["_rank_order", "判定", "優先度", "競馬場", "_Rnum", "_馬番"] if c in out.columns]
        out = out.sort_values(sort_cols).drop(columns=["_rank_order", "_Rnum", "_馬番"]).reset_index(drop=True)
    return out, sorted(unknown_sires), sorted(unknown_damsires)


# =========================
# 最終出力画像
# =========================
def _find_jp_font(size=42, bold=False):
    if ImageFont is None:
        return None
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc" if bold else "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "C:/Windows/Fonts/YuGothB.ttc" if bold else "C:/Windows/Fonts/YuGothR.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
    ]
    for p in candidates:
        try:
            if p and Path(p).exists():
                return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def _text_size(draw, text, font):
    try:
        b = draw.textbbox((0, 0), str(text), font=font)
        return b[2] - b[0], b[3] - b[1]
    except Exception:
        return draw.textsize(str(text), font=font)


def _fit_font(draw, text, max_width, size, bold=False, min_size=24):
    for s in range(size, min_size - 1, -2):
        f = _find_jp_font(s, bold=bold)
        if _text_size(draw, text, f)[0] <= max_width:
            return f
    return _find_jp_font(min_size, bold=bold)


def _draw_center(draw, xy, text, font, fill):
    x, y, w, h = xy
    tw, th = _text_size(draw, text, font)
    draw.text((x + (w - tw) / 2, y + (h - th) / 2 - 2), text, font=font, fill=fill)


def _draw_right(draw, x, y, text, font, fill):
    tw, th = _text_size(draw, text, font)
    draw.text((x - tw, y), text, font=font, fill=fill)


def create_teppan_image(simple_df):
    if Image is None:
        raise RuntimeError("Pillow が利用できません。requirements.txt に pillow を追加してください。")

    df = simple_df.copy()
    if df.empty:
        raise RuntimeError("画像化する該当馬がありません。")

    for c in ["競馬場", "R", "馬番", "馬名", "鉄板ランク"]:
        if c not in df.columns:
            df[c] = ""
    df["_Rnum"] = df["R"].map(r_num).fillna(999)
    df["_馬番"] = df["馬番"].map(r_num).fillna(999)

    sections = [
        ("超鉄板", "超鉄板⭐️", (172, 0, 18), (255, 255, 255)),
        ("強鉄板", "強鉄板⭐️", (205, 161, 0), (40, 31, 0)),
        ("鉄板", "鉄板⭐️", (60, 68, 82), (255, 255, 255)),
    ]
    section_rows = []
    for title, rank, color, title_text in sections:
        sub = df[df["鉄板ランク"].map(norm_text) == rank].copy()
        sub = sub.sort_values(["競馬場", "_Rnum", "_馬番"])
        if not sub.empty:
            section_rows.append((title, rank, color, title_text, sub))

    if not section_rows:
        # 想定外のランク名でも表示できるようにする
        sub = df.sort_values(["競馬場", "_Rnum", "_馬番"])
        section_rows.append(("鉄板", "", (60, 68, 82), (255, 255, 255), sub))

    W = 1200
    top_h = 360
    sec_header_h = 130
    row_h = 130
    gap = 45
    bottom_h = 80
    card_margin = 58
    card_radius = 26
    total_rows = sum(len(x[4]) for x in section_rows)
    H = top_h + len(section_rows) * sec_header_h + total_rows * row_h + max(0, len(section_rows) - 1) * gap + bottom_h + 50
    H = max(H, 900)

    img = Image.new("RGB", (W, H), (255, 253, 247))
    draw = ImageDraw.Draw(img)

    # 外枠
    gold = (192, 148, 25)
    draw.rounded_rectangle([10, 10, W - 10, H - 10], radius=24, outline=gold, width=3)

    # 上部タイトル
    title_font = _find_jp_font(60, bold=True)
    subtitle_font = _find_jp_font(82, bold=True)
    small_font = _find_jp_font(32, bold=False)
    _draw_center(draw, (0, 60, W, 80), "鉄板 ★ 血統アプリ", title_font, (17, 24, 39))
    _draw_center(draw, (0, 165, W, 90), "最終出力イメージ", subtitle_font, (111, 70, 0))
    draw.line([130, 315, 520, 315], fill=gold, width=3)
    draw.line([680, 315, W - 130, 315], fill=gold, width=3)
    _draw_center(draw, (520, 287, 160, 60), "◆ ◇ ◆", small_font, gold)

    y = top_h
    row_font = _find_jp_font(50, bold=True)
    horse_font_base = 50
    num_font = _find_jp_font(58, bold=True)
    section_font = _find_jp_font(72, bold=True)

    for si, (title, rank, sec_color, title_text, sub) in enumerate(section_rows):
        if si > 0:
            y += gap
        x0 = card_margin
        x1 = W - card_margin
        card_h = sec_header_h + len(sub) * row_h
        # カード影
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle([x0 + 4, y + 8, x1 + 4, y + card_h + 8], radius=card_radius, fill=(0, 0, 0, 35))
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        img.paste(Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB"))
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle([x0, y, x1, y + card_h], radius=card_radius, fill=(255, 255, 255), outline=(229, 202, 126), width=2)
        draw.rounded_rectangle([x0, y, x1, y + sec_header_h], radius=card_radius, fill=sec_color)
        draw.rectangle([x0, y + sec_header_h - card_radius, x1, y + sec_header_h], fill=sec_color)
        _draw_center(draw, (x0, y + 8, x1 - x0, sec_header_h - 16), f"‹  {title}  ›", section_font, title_text)

        yy = y + sec_header_h
        for i, (_, r) in enumerate(sub.iterrows()):
            if i > 0:
                draw.line([x0 + 40, yy, x1 - 40, yy], fill=(226, 226, 226), width=2)
            place = norm_text(r.get("競馬場", ""))
            rr = r_num(r.get("R", ""))
            horse_no = r_num(r.get("馬番", ""))
            horse = str(r.get("馬名", ""))

            draw.text((x0 + 58, yy + 38), place, font=row_font, fill=(15, 23, 42))
            r_text = f"{rr}R" if rr is not None else f"{r.get('R', '')}R"
            draw.text((x0 + 250, yy + 38), r_text, font=row_font, fill=(15, 23, 42))

            box_x, box_y, box_w, box_h = x0 + 430, yy + 25, 88, 82
            draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=14, fill=sec_color)
            _draw_center(draw, (box_x, box_y, box_w, box_h), str(horse_no or r.get("馬番", "")), num_font, (255, 255, 255))

            h_font = _fit_font(draw, horse, x1 - (x0 + 575) - 40, horse_font_base, bold=True, min_size=32)
            draw.text((x0 + 575, yy + 40), horse, font=h_font, fill=(15, 23, 42))
            yy += row_h
        y += card_h

    note_font = _find_jp_font(28, bold=False)
    _draw_center(draw, (0, H - 72, W, 40), "※画像は表示イメージです", note_font, (80, 80, 80))

    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()


def make_composite_df(result):
    composite_cols = ["日付", "競馬場", "R", "レース名", "馬番", "馬名", "鉄板ランク", "判定", "印"]
    simple_df = result.copy()
    for c in composite_cols:
        if c not in simple_df.columns:
            simple_df[c] = ""
    simple_df["R_num"] = simple_df["R"].map(r_num)
    simple_df = simple_df[simple_df["R_num"].between(7, 12, inclusive="both")].copy()

    def rank_priority(v):
        s = norm_text(v)
        if s == "超鉄板⭐️":
            return 1
        if s == "強鉄板⭐️":
            return 2
        if s == "鉄板⭐️":
            return 3
        return 9

    def to_float(v):
        try:
            m = re.search(r"-?\d+(?:\.\d+)?", str(v))
            return float(m.group(0)) if m else 0.0
        except Exception:
            return 0.0

    simple_df["_rank_priority"] = simple_df["鉄板ランク"].map(rank_priority)
    simple_df["_fukusho"] = simple_df["検証複勝率%"].map(to_float) if "検証複勝率%" in simple_df.columns else 0.0
    simple_df["_lift"] = simple_df["リフト"].map(to_float) if "リフト" in simple_df.columns else 0.0
    simple_df["_horse_no"] = simple_df["馬番"].map(r_num).fillna(999)

    simple_df = (
        simple_df
        .sort_values(["日付", "競馬場", "R_num", "_rank_priority", "_fukusho", "_lift", "_horse_no"],
                     ascending=[True, True, True, True, False, False, True])
        .drop_duplicates(subset=["日付", "競馬場", "R", "馬番", "馬名"], keep="first")
        .copy()
    )

    mark_list = ["◎", "○", "▲", "△", "☆", "注"]
    simple_df["印"] = ""
    for _, idxs in simple_df.groupby(["日付", "競馬場", "R"], dropna=False).groups.items():
        for i, idx in enumerate(list(idxs)):
            simple_df.loc[idx, "印"] = mark_list[i] if i < len(mark_list) else "他"

    simple_df = simple_df.sort_values(["日付", "競馬場", "R_num", "_rank_priority", "_fukusho", "_lift", "_horse_no"],
                                      ascending=[True, True, True, True, False, False, True]).copy()
    return simple_df[composite_cols]


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
    st.code(f"ロジック辞書: {logic_path.name if logic_path else '未検出'}\nコース判定: {course_path.name if course_path else '未検出'}")

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

with st.expander("血統タイプ変換表の読み込み状況", expanded=True):
    st.caption("ここで 血統タイプ変換表.csv が見えているか、列名が認識できているか確認できます。")
    conv_diag = diagnose_bloodline_conversion_files()
    if conv_diag.empty:
        st.warning("血統タイプ変換表候補のCSVが見つかりません。ファイル名に「血統タイプ変換」を含めて、app.pyと同じ場所に置いてください。例：血統タイプ変換表.csv")
    else:
        st.dataframe(conv_diag, use_container_width=True, hide_index=True)
    st.info("父タイプ名・母父タイプ名が入力CSVにある場合はそれを優先します。空欄の場合は app.py 内の固定辞書＋血統タイプ変換表.csv で補完します。")

st.subheader("予想CSV貼り付け")
st.info("予想CSVはGitHubに置かず、画面内で貼り付けるか、CSVファイルを読み込んでください。父タイプ名が空欄でも、種牡馬があれば一部自動補完します。")

with st.expander("TARGETから抜く推奨列を見る", expanded=True):
    st.code("""ヘッダーありの場合:
日付,場,R,レース名,芝ダ,距離,馬番,馬名,種牡馬,父タイプ名,母父名,母父タイプ名,性別,年齢,斤量,頭数,前走馬場状態,前芝・ダ,前距離,前走斤量,休み明け～戦目,所属,調教師,騎手,前騎手,前走着順,前走着差

ヘッダーなしTARGET出力もそのまま読み込めます。""", language="csv")
    st.caption("結果は詳細版CSV、複合アプリ用9列CSV、最終出力PNG画像で出力できます。複合アプリ用CSVと画像は7〜12Rのみです。")

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
    csv_text = st.text_area("予想に必要な項目CSVをここに貼り付け", height=260, placeholder="日付,場所,R,レース名,芝・ダ,距離,馬番,馬名,種牡馬,父タイプ名,母父名,母父タイプ名,...")

st.subheader("天気・馬場状態の選択補完")
st.caption("TARGETから天気・馬場状態が取れない場合だけ使います。競馬場ごとに芝・ダを選んで、天気と馬場状態を指定できます。")

manual_rows = []
with st.expander("競馬場・芝ダごとに指定する", expanded=True):
    st.caption("最大3会場まで同時指定できます。天気は会場ごとに1つ、馬場状態は芝・ダで別々に指定できます。")
    racecourse_options = ["", "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]
    weather_options = ["", "晴", "曇", "雨", "小雨", "雪"]
    going_options = ["", "良", "稍重", "重", "不良"]

    for i in range(1, 4):
        st.markdown(f"**会場{i}**")
        c0, c1 = st.columns([1.25, 1.1])
        with c0:
            place = st.selectbox(f"競馬場{i}", racecourse_options, index=0, key=f"manual_place_{i}")
        with c1:
            weather = st.selectbox(f"天気{i}", weather_options, index=0, key=f"manual_weather_{i}")
        st.caption("馬場状態")
        c2, c3 = st.columns(2)
        with c2:
            turf_going = st.selectbox(f"芝 馬場状態{i}", going_options, index=0, key=f"manual_turf_going_{i}")
        with c3:
            dirt_going = st.selectbox(f"ダ 馬場状態{i}", going_options, index=0, key=f"manual_dirt_going_{i}")
        if place:
            if weather or turf_going:
                manual_rows.append({"競馬場": place, "芝ダ": "芝", "天気": weather, "馬場状態": turf_going})
            if weather or dirt_going:
                manual_rows.append({"競馬場": place, "芝ダ": "ダ", "天気": weather, "馬場状態": dirt_going})

manual_condition_csv = pd.DataFrame(manual_rows).to_csv(index=False) if manual_rows else ""
with st.expander("補完内容を確認", expanded=False):
    if manual_condition_csv:
        st.code(manual_condition_csv, language="csv")
    else:
        st.caption("補完指定はありません。天気・馬場状態条件は空欄ならスキップされます。")

run = st.button("鉄板⭐️候補を抽出", type="primary", use_container_width=True)

if run:
    try:
        file_obj = uploaded_file if uploaded_file is not None else st.session_state.get("prediction_upload", None)
        if file_obj is not None:
            input_df = read_csv_smart(file_obj)
        elif csv_text.strip():
            input_df = read_csv_smart(io.StringIO(csv_text))
        else:
            st.warning("CSVファイルを選択するか、CSV本文を貼り付けてください。")
            st.stop()

        input_df = apply_manual_conditions(input_df, "", "", manual_condition_csv)
        result, unknown_sires, unknown_damsires = build_result(input_df, logic_df, course_df, use_statuses)

        loaded_map_files = st.session_state.get("bloodline_type_map_loaded_files", [])
        with st.expander("実際に読み込んだ血統タイプ変換表", expanded=False):
            if loaded_map_files:
                st.dataframe(pd.DataFrame(loaded_map_files), use_container_width=True, hide_index=True)
            else:
                st.caption("外部の血統タイプ変換表は読み込まれていません。app.py内の固定辞書のみで補完しています。")

        if unknown_sires or unknown_damsires:
            with st.expander("系統に変換できなかった種牡馬/母父を見る", expanded=False):
                if unknown_sires:
                    st.write("未変換の種牡馬")
                    st.code("\n".join(unknown_sires[:300]))
                if unknown_damsires:
                    st.write("未変換の母父")
                    st.code("\n".join(unknown_damsires[:300]))
                st.caption("必要なら、app.pyと同じ場所に 血統タイプ変換表.csv を置くと補完できます。列は 種牡馬名,タイプ名 などでOKです。")

        if result.empty:
            st.warning("該当馬はありませんでした。採用のみで出ない場合は、設定で保留も含めて確認してください。")
        else:
            st.success(f"該当馬 {len(result)}件を抽出しました。")
            if "鉄板ランク" in result.columns:
                st.subheader("鉄板ランク内訳")
                rank_counts = result["鉄板ランク"].value_counts().reindex(["超鉄板⭐️", "強鉄板⭐️", "鉄板⭐️"]).fillna(0).astype(int)
                st.dataframe(rank_counts.rename("頭数").reset_index().rename(columns={"index": "鉄板ランク"}), use_container_width=True, hide_index=True)

            st.subheader("抽出結果")
            st.dataframe(result, use_container_width=True, hide_index=True)

            csv_out = result.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("結果CSVをダウンロード（詳細版）", csv_out, file_name="teppan_bloodline_result.csv", mime="text/csv", use_container_width=True)

            simple_df = make_composite_df(result)
            simple_csv = simple_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("結果CSVをダウンロード（複合アプリ用・7〜12R）", simple_csv, file_name="teppan_bloodline_result_for_composite_7-12R.csv", mime="text/csv", use_container_width=True)

            st.subheader("最終出力画像")
            if simple_df.empty:
                st.warning("7〜12Rの該当馬がないため、最終出力画像は作成されません。")
            else:
                try:
                    png_bytes = create_teppan_image(simple_df)
                    st.image(png_bytes, caption="鉄板⭐️血統アプリ 最終出力画像", use_container_width=True)
                    st.download_button("最終出力画像をダウンロード（PNG）", png_bytes, file_name="teppan_bloodline_final_output.png", mime="image/png", use_container_width=True)
                except Exception as img_e:
                    st.error("画像作成中にエラーが出ました。")
                    st.exception(img_e)
                    st.info("Pillow が無い場合は requirements.txt に pillow を追加してください。")

            with st.expander("コピー用CSV（詳細版）", expanded=False):
                st.code(csv_out, language="csv")
            with st.expander("コピー用CSV（複合アプリ用・7〜12R・印付き）", expanded=False):
                st.code(simple_csv, language="csv")

    except Exception as e:
        st.error("処理中にエラーが出ました。")
        st.exception(e)
