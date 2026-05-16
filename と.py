import io
import re
import base64
import html
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
st.caption("GitHubに置くCSVはロジック辞書とコース判定の2つだけです。予想CSVは画面内に貼り付けます。種牡馬/母父名から系統を自動補完できます。最終出力画像も作成できます。SVG出力に対応しています。")

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
# 最終出力画像（SVGメイン）
# =========================
def svg_escape(s):
    return html.escape(str(s if s is not None else ""))


def create_teppan_svg(simple_df):
    df = simple_df.copy()
    if df.empty:
        raise RuntimeError("画像化する該当馬がありません。")

    for c in ["競馬場", "R", "馬番", "馬名", "鉄板ランク"]:
        if c not in df.columns:
            df[c] = ""

    df["_Rnum"] = df["R"].map(r_num).fillna(999)
    df["_馬番"] = df["馬番"].map(r_num).fillna(999)

    sections = [
        ("超鉄板", "超鉄板⭐️", "#b40012", "#ffffff"),
        ("強鉄板", "強鉄板⭐️", "#d2a100", "#1f1a05"),
        ("鉄板", "鉄板⭐️", "#3c4452", "#ffffff"),
    ]

    section_rows = []
    for title, rank, color, title_text in sections:
        sub = df[df["鉄板ランク"].map(norm_text) == rank].copy()
        sub = sub.sort_values(["競馬場", "_Rnum", "_馬番"])
        if not sub.empty:
            section_rows.append((title, color, title_text, sub))

    if not section_rows:
        sub = df.sort_values(["競馬場", "_Rnum", "_馬番"]).copy()
        section_rows.append(("鉄板", "#3c4452", "#ffffff", sub))

    W = 900
    top_h = 290
    sec_header_h = 104
    row_h = 106
    gap = 34
    bottom_h = 70
    card_margin = 42
    card_radius = 22
    total_rows = sum(len(x[3]) for x in section_rows)
    H = top_h + len(section_rows) * sec_header_h + total_rows * row_h + max(0, len(section_rows) - 1) * gap + bottom_h + 36
    H = max(H, 900)

    svg_parts = []
    add = svg_parts.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    add(
        """
    <defs>
      <linearGradient id="bgGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#fffdfa" />
        <stop offset="100%" stop-color="#f9f5ec" />
      </linearGradient>
      <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="5" stdDeviation="8" flood-color="#000000" flood-opacity="0.16"/>
      </filter>
      <style>
        .jp { font-family: 'Hiragino Sans', 'Yu Gothic', 'Meiryo', 'Noto Sans JP', sans-serif; }
        .title1 { font-size: 52px; font-weight: 800; fill: #0f172a; }
        .title2 { font-size: 76px; font-weight: 900; fill: #7a4f00; }
        .sectionTitleW { font-size: 62px; font-weight: 900; fill: #ffffff; letter-spacing: 1px; }
        .sectionTitleD { font-size: 62px; font-weight: 900; fill: #1f1a05; letter-spacing: 1px; }
        .rowPlace { font-size: 34px; font-weight: 800; fill: #0f172a; }
        .rowR { font-size: 34px; font-weight: 800; fill: #0f172a; }
        .rowNum { font-size: 44px; font-weight: 900; fill: #ffffff; }
        .rowHorse { font-size: 34px; font-weight: 800; fill: #0f172a; }
        .note { font-size: 22px; fill: #666666; }
        .orn { font-size: 22px; fill: #c09419; }
      </style>
    </defs>
    """
    )
    add(f'<rect x="0" y="0" width="{W}" height="{H}" rx="28" fill="url(#bgGrad)"/>')
    add(f'<rect x="10" y="10" width="{W-20}" height="{H-20}" rx="24" fill="none" stroke="#c09419" stroke-width="3"/>')
    add(f'<text x="{W/2}" y="92" text-anchor="middle" class="jp title1">鉄板★血統アプリ</text>')
    add(f'<text x="{W/2}" y="188" text-anchor="middle" class="jp title2">最終出力イメージ</text>')
    add(f'<line x1="130" y1="252" x2="360" y2="252" stroke="#c09419" stroke-width="3"/>')
    add(f'<line x1="540" y1="252" x2="770" y2="252" stroke="#c09419" stroke-width="3"/>')
    add(f'<text x="{W/2}" y="260" text-anchor="middle" class="jp orn">◆ ◇ ◆</text>')

    y = top_h
    for sec_idx, (title, sec_color, title_text, sub) in enumerate(section_rows):
        if sec_idx > 0:
            y += gap
        x0 = card_margin
        x1 = W - card_margin
        card_h = sec_header_h + len(sub) * row_h
        card_w = x1 - x0

        add('<g filter="url(#shadow)">')
        add(f'<rect x="{x0}" y="{y}" width="{card_w}" height="{card_h}" rx="{card_radius}" fill="#ffffff" stroke="#e5ca7e" stroke-width="2"/>')
        add(f'<path d="M {x0+card_radius} {y} H {x1-card_radius} A {card_radius} {card_radius} 0 0 1 {x1} {y+card_radius} V {y+sec_header_h} H {x0} V {y+card_radius} A {card_radius} {card_radius} 0 0 1 {x0+card_radius} {y} Z" fill="{sec_color}"/>')
        add('</g>')

        cls = "sectionTitleD" if title_text == "#1f1a05" else "sectionTitleW"
        add(f'<text x="{W/2}" y="{y+70}" text-anchor="middle" class="jp {cls}">{svg_escape(title)}</text>')

        yy = y + sec_header_h
        for i, (_, r) in enumerate(sub.iterrows()):
            if i > 0:
                add(f'<line x1="{x0+34}" y1="{yy}" x2="{x1-34}" y2="{yy}" stroke="#e5e5e5" stroke-width="2"/>')
            place = norm_text(r.get("競馬場", ""))
            rr = r_num(r.get("R", ""))
            horse_no = r_num(r.get("馬番", ""))
            horse = svg_escape(r.get("馬名", ""))
            r_text = f"{rr}R" if rr is not None else f"{svg_escape(r.get('R', ''))}R"
            num_text = str(horse_no if horse_no is not None else r.get("馬番", ""))

            base_y = yy + 64
            add(f'<text x="{x0+42}" y="{base_y}" class="jp rowPlace">{svg_escape(place)}</text>')
            add(f'<text x="{x0+188}" y="{base_y}" class="jp rowR">{svg_escape(r_text)}</text>')

            box_x, box_y, box_w, box_h = x0 + 336, yy + 18, 82, 70
            add(f'<rect x="{box_x}" y="{box_y}" width="{box_w}" height="{box_h}" rx="12" fill="{sec_color}"/>')
            add(f'<text x="{box_x + box_w/2}" y="{box_y + 49}" text-anchor="middle" class="jp rowNum">{svg_escape(num_text)}</text>')
            add(f'<text x="{x0+456}" y="{base_y}" class="jp rowHorse">{horse}</text>')
            yy += row_h

        y += card_h

    add(f'<text x="{W/2}" y="{H-28}" text-anchor="middle" class="jp note">※画像は表示イメージです</text>')
    add('</svg>')
    return ''.join(svg_parts)


def render_svg_html(svg_text, max_width=740):
    svg_b64 = base64.b64encode(svg_text.encode("utf-8")).decode("ascii")
    return f"""
    <div style=\"display:flex;justify-content:center;\">
      <img src=\"data:image/svg+xml;base64,{svg_b64}\" style=\"width:100%;max-width:{max_width}px;height:auto;border-radius:16px;\" />
    </div>
    """


# 旧PNG描画関数は残す（任意利用）
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


def _draw_center(draw, xy, text, font, fill):
    x, y, w, h = xy
    tw, th = _text_size(draw, text, font)
    draw.text((x + (w - tw) / 2, y + (h - th) / 2 - 2), text, font=font, fill=fill)


def create_teppan_image(simple_df):
    if Image is None:
        raise RuntimeError("Pillow が利用できません。")

    df = simple_df.copy()
    if df.empty:
        raise RuntimeError("画像化する該当馬がありません。")

    for c in ["競馬場", "R", "馬番", "馬名", "鉄板ランク"]:
        if c not in df.columns:
            df[c] = ""
    df["_Rnum"] = df["R"].map(r_num).fillna(999)
    df["_馬番"] = df["馬番"].map(r_num).fillna(999)

    sections = [("超鉄板", "超鉄板⭐️", (172, 0, 18), (255, 255, 255)), ("強鉄板", "強鉄板⭐️", (205, 161, 0), (40, 31, 0)), ("鉄板", "鉄板⭐️", (60, 68, 82), (255, 255, 255))]
    section_rows = []
    for title, rank, color, title_text in sections:
        sub = df[df["鉄板ランク"].map(norm_text) == rank].copy().sort_values(["競馬場", "_Rnum", "_馬番"])
        if not sub.empty:
            section_rows.append((title, rank, color, title_text, sub))
    if not section_rows:
        sub = df.sort_values(["競馬場", "_Rnum", "_馬番"])
        section_rows.append(("鉄板", "", (60, 68, 82), (255, 255, 255), sub))

    W = 900
    top_h = 280
    sec_header_h = 100
    row_h = 102
    gap = 28
    bottom_h = 60
    card_margin = 42
    H = top_h + len(section_rows) * sec_header_h + sum(len(x[4]) for x in section_rows) * row_h + max(0, len(section_rows) - 1) * gap + bottom_h
    img = Image.new("RGB", (W, H), (255, 253, 247))
    draw = ImageDraw.Draw(img)
    gold = (192, 148, 25)
    draw.rounded_rectangle([10, 10, W - 10, H - 10], radius=24, outline=gold, width=3)
    _draw_center(draw, (0, 56, W, 72), "鉄板★血統アプリ", _find_jp_font(50, True), (17, 24, 39))
    _draw_center(draw, (0, 145, W, 82), "最終出力イメージ", _find_jp_font(70, True), (122, 79, 0))

    y = top_h
    for si, (title, rank, sec_color, title_text, sub) in enumerate(section_rows):
        if si > 0:
            y += gap
        x0 = card_margin
        x1 = W - card_margin
        card_h = sec_header_h + len(sub) * row_h
        draw.rounded_rectangle([x0, y, x1, y + card_h], radius=22, fill=(255, 255, 255), outline=(229, 202, 126), width=2)
        draw.rounded_rectangle([x0, y, x1, y + sec_header_h], radius=22, fill=sec_color)
        draw.rectangle([x0, y + sec_header_h - 22, x1, y + sec_header_h], fill=sec_color)
        _draw_center(draw, (x0, y, x1 - x0, sec_header_h), title, _find_jp_font(58, True), title_text)
        yy = y + sec_header_h
        for i, (_, r) in enumerate(sub.iterrows()):
            if i > 0:
                draw.line([x0 + 30, yy, x1 - 30, yy], fill=(226, 226, 226), width=2)
            place = norm_text(r.get("競馬場", ""))
            rr = r_num(r.get("R", ""))
            horse_no = r_num(r.get("馬番", ""))
            horse = str(r.get("馬名", ""))
            draw.text((x0 + 42, yy + 34), place, font=_find_jp_font(34, True), fill=(15, 23, 42))
            draw.text((x0 + 178, yy + 34), f"{rr}R" if rr is not None else str(r.get("R", "")), font=_find_jp_font(34, True), fill=(15, 23, 42))
            bx, by = x0 + 336, yy + 16
            draw.rounded_rectangle([bx, by, bx + 82, by + 68], radius=12, fill=sec_color)
            _draw_center(draw, (bx, by, 82, 68), str(horse_no or r.get("馬番", "")), _find_jp_font(42, True), (255, 255, 255))
            draw.text((x0 + 452, yy + 35), horse, font=_find_jp_font(34, True), fill=(15, 23, 42))
            yy += row_h
        y += card_h

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
    st.caption("結果は詳細版CSV、複合アプリ用9列CSV、最終出力SVG画像で出力できます。複合アプリ用CSVと画像は7〜12Rのみです。")

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
                    svg_text = create_teppan_svg(simple_df)
                    st.markdown(render_svg_html(svg_text), unsafe_allow_html=True)
                    st.download_button(
                        "最終出力画像をダウンロード（SVG）",
                        svg_text.encode("utf-8"),
                        file_name="teppan_bloodline_final_output.svg",
                        mime="image/svg+xml",
                        use_container_width=True,
                    )

                    with st.expander("PNGでも保存したい場合", expanded=False):
                        if Image is None:
                            st.info("PNG出力は Pillow 未導入のため利用できません。SVG版をご利用ください。")
                        else:
                            try:
                                png_bytes = create_teppan_image(simple_df)
                                st.image(png_bytes, caption="PNGプレビュー", use_container_width=True)
                                st.download_button(
                                    "最終出力画像をダウンロード（PNG）",
                                    png_bytes,
                                    file_name="teppan_bloodline_final_output.png",
                                    mime="image/png",
                                    use_container_width=True,
                                )
                            except Exception as png_e:
                                st.info("PNG生成はスキップしました。SVG版は利用できます。")
                                st.exception(png_e)
                except Exception as img_e:
                    st.error("画像作成中にエラーが出ました。")
                    st.exception(img_e)
                    st.info("まずはSVG版をご確認ください。")

            with st.expander("コピー用CSV（詳細版）", expanded=False):
                st.code(csv_out, language="csv")
            with st.expander("コピー用CSV（複合アプリ用・7〜12R・印付き）", expanded=False):
                st.code(simple_csv, language="csv")

    except Exception as e:
        st.error("処理中にエラーが出ました。")
        st.exception(e)
