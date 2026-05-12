import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="鉄板⭐️血統アプリ", layout="wide")

st.title("鉄板⭐️血統アプリ")
st.caption("GitHubに置くCSVはロジック辞書とコース判定の2つだけです。予想CSVは画面内に貼り付けます。")

def read_csv_smart(path_or_buf):
    encodings = ["utf-8-sig", "utf-8", "cp932", "shift_jis"]
    last_err = None
    for enc in encodings:
        try:
            if isinstance(path_or_buf, (str, Path)):
                return pd.read_csv(path_or_buf, encoding=enc)
            path_or_buf.seek(0)
            return pd.read_csv(path_or_buf, encoding=enc)
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
    s = s.replace("芝・ダ", "芝ダ").replace("芝ダート", "芝ダ")
    return s

def normalize_df(df):
    df = df.copy()
    df.columns = [norm_col(c) for c in df.columns]

    rename_map = {
        "場所": "競馬場",
        "レース番号": "R",
        "馬番号": "馬番",
        "父系統": "父タイプ名",
        "母父系統": "母父タイプ名",
        "前走芝ダ": "前芝ダ",
        "前芝・ダ": "前芝ダ",
        "前走距離": "前距離",
        "前走馬場": "前走馬場状態",
        "芝・ダ": "芝ダ",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    if "前芝ダ" in df.columns and "前芝・ダ" not in df.columns:
        df["前芝・ダ"] = df["前芝ダ"]

    if "前走所属" not in df.columns and "所属" in df.columns:
        df["前走所属"] = df["所属"]

    return df

def csv_files():
    return sorted(Path(".").glob("*.csv"), key=lambda p: p.name)

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
        "前芝・ダ": "前芝・ダ",
    }
    lookup = item_map.get(item, item)

    if lookup == "前走所属" and lookup not in row.index and "所属" in row.index:
        lookup = "所属"

    if lookup not in row.index:
        return False

    actual = norm_text(row.get(lookup, ""))
    if actual == "":
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

def build_result(input_df, logic_df, course_df, use_statuses):
    input_df = normalize_df(input_df)
    logic_df = normalize_df(logic_df)
    course_df = normalize_df(course_df)

    required = ["競馬場", "芝ダ", "距離", "馬名", "父タイプ名", "母父タイプ名"]
    missing = [c for c in required if c not in input_df.columns]
    if missing:
        raise ValueError("入力CSVに不足列があります: " + ", ".join(missing))

    for df in [input_df, logic_df, course_df]:
        for c in ["競馬場", "芝ダ", "距離"]:
            if c in df.columns:
                df[c] = df[c].map(norm_text)

    use_statuses_norm = [norm_text(x) for x in use_statuses]
    course_use = course_df[course_df["判定"].astype(str).map(norm_text).isin(use_statuses_norm)].copy()

    results = []

    for _, h in input_df.iterrows():
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
                "血統区分": hit_blood_type,
                "該当系統": hit_system,
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
        sort_cols = [c for c in ["判定", "優先度", "競馬場", "R", "馬番"] if c in out.columns]
        out = out.sort_values(sort_cols).reset_index(drop=True)
    return out

logic_path, course_path = detect_files()

with st.sidebar:
    st.header("設定")
    use_statuses = st.multiselect(
        "使用するコース判定",
        ["採用", "保留", "除外"],
        default=["採用"],
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
    st.write("CSVは app.py と同じ場所にありますが、列名で判定できていません。")
    st.write("必要な2種類:")
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
st.info("予想CSVはGitHubに置かず、この下の入力欄に貼り付けてください。")

with st.expander("貼り付けCSVの必要列を見る", expanded=True):
    st.code(
        "日付,競馬場,R,レース名,芝ダ,距離,馬番,馬名,父タイプ名,母父タイプ名,性別,年齢,所属,斤量,頭数,天気,馬場状態,前芝・ダ,前距離,前走馬場状態,前走斤量,替,休み明け〜戦目",
        language="csv",
    )
    st.caption("前走所属がない場合は所属で代替します。馬体重増減は未使用です。")

csv_text = st.text_area(
    "予想に必要な項目CSVをここに貼り付け",
    height=300,
    placeholder="日付,競馬場,R,レース名,芝ダ,距離,馬番,馬名,父タイプ名,母父タイプ名,...",
)

run = st.button("鉄板⭐️候補を抽出", type="primary", use_container_width=True)

if run:
    if not csv_text.strip():
        st.warning("CSV本文を貼り付けてください。")
        st.stop()

    try:
        input_df = read_csv_smart(io.StringIO(csv_text))
        result = build_result(input_df, logic_df, course_df, use_statuses)

        if result.empty:
            st.warning("該当馬はありませんでした。採用のみで出ない場合は、設定で保留も含めて確認してください。")
        else:
            st.success(f"該当馬 {len(result)}件を抽出しました。")
            st.dataframe(result, use_container_width=True, hide_index=True)
            csv_out = result.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "結果CSVをダウンロード",
                csv_out,
                file_name="teppan_bloodline_result.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.subheader("コピー用CSV")
            st.code(csv_out, language="csv")

    except Exception as e:
        st.error("処理中にエラーが出ました。")
        st.exception(e)
