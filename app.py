import io
import pandas as pd
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="鉄板⭐️血統アプリ", layout="wide")

LOGIC_FILE = "鉄板血統_TOP5並列_修正版_最終ロジック辞書.csv"
COURSE_FILE = "鉄板血統_コース別_採用保留除外判定.csv"

st.title("鉄板⭐️血統アプリ")
st.caption("予想用CSVを貼り付けるだけで、コース別採用/保留/除外＋血統ロジックに該当する馬を抽出します。")


def read_csv_smart(path_or_buf):
    encodings = ["utf-8-sig", "utf-8", "cp932"]
    last_err = None
    for enc in encodings:
        try:
            if isinstance(path_or_buf, (str, Path)):
                return pd.read_csv(path_or_buf, encoding=enc)
            else:
                path_or_buf.seek(0)
                return pd.read_csv(path_or_buf, encoding=enc)
        except Exception as e:
            last_err = e
    raise last_err


def norm_col_name(s):
    s = str(s).strip()
    s = s.replace("芝・ダ", "芝ダ")
    s = s.replace("芝ダート", "芝ダ")
    return s


def norm_val(v):
    if pd.isna(v):
        return ""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.replace("　", " ").strip()
    return s


def normalize_df(df):
    df = df.copy()
    df.columns = [norm_col_name(c) for c in df.columns]
    # よくある列名ゆれを吸収
    rename_map = {
        "場所": "競馬場",
        "レース番号": "R",
        "馬番号": "馬番",
        "父系統": "父タイプ名",
        "母父系統": "母父タイプ名",
        "前芝ダ": "前芝ダ",
        "前走芝ダ": "前芝ダ",
        "前芝・ダ": "前芝ダ",
        "前走距離": "前距離",
        "前走馬場": "前走馬場状態",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    # アプリ内条件名に合わせる
    if "前芝ダ" in df.columns and "前芝・ダ" not in df.columns:
        df["前芝・ダ"] = df["前芝ダ"]
    if "前走所属" not in df.columns and "所属" in df.columns:
        df["前走所属"] = df["所属"]
    return df


def match_value(row, item, expected):
    item = norm_val(item)
    expected = norm_val(expected)
    if item == "" or expected == "":
        return True

    # 前走所属がない場合は所属で代替
    lookup_item = item
    if item == "前走所属" and "前走所属" not in row.index and "所属" in row.index:
        lookup_item = "所属"

    if lookup_item not in row.index:
        return False

    actual = norm_val(row.get(lookup_item, ""))
    if actual == "":
        return False

    # TARGET側の「替=*」は、* または空欄以外を許容
    if item == "替" and expected == "*":
        return actual == "*" or actual != ""

    return actual == expected


def rule_conditions(rule):
    conds = []
    for i in range(1, 9):
        item = rule.get(f"条件{i}項目", "")
        content = rule.get(f"条件{i}内容", "")
        if norm_val(item) and norm_val(content):
            conds.append((i, norm_val(item), norm_val(content)))
    return conds


def horse_system(row, blood_type):
    if norm_val(blood_type) == "父系":
        return norm_val(row.get("父タイプ名", ""))
    if norm_val(blood_type) == "母父系":
        return norm_val(row.get("母父タイプ名", ""))
    return ""


def build_result(input_df, logic_df, course_df, use_statuses):
    input_df = normalize_df(input_df)
    logic_df = normalize_df(logic_df)
    course_df = normalize_df(course_df)

    required = ["競馬場", "芝ダ", "距離", "馬名", "父タイプ名", "母父タイプ名"]
    missing = [c for c in required if c not in input_df.columns]
    if missing:
        raise ValueError("入力CSVに不足列があります: " + ", ".join(missing))

    course_use = course_df[course_df["判定"].astype(str).isin(use_statuses)].copy()
    course_keys = set(
        tuple(norm_val(x) for x in row)
        for row in course_use[["競馬場", "芝ダ", "距離"]].values.tolist()
    )

    results = []
    for _, h in input_df.iterrows():
        course_key = (norm_val(h.get("競馬場")), norm_val(h.get("芝ダ")), norm_val(h.get("距離")))
        if course_key not in course_keys:
            continue

        rules = logic_df[
            (logic_df["競馬場"].map(norm_val) == course_key[0]) &
            (logic_df["芝ダ"].map(norm_val) == course_key[1]) &
            (logic_df["距離"].map(norm_val) == course_key[2])
        ]
        if rules.empty:
            continue

        course_row = course_use[
            (course_use["競馬場"].map(norm_val) == course_key[0]) &
            (course_use["芝ダ"].map(norm_val) == course_key[1]) &
            (course_use["距離"].map(norm_val) == course_key[2])
        ].iloc[0]

        for _, r in rules.iterrows():
            blood_type = norm_val(r.get("血統区分"))
            sys_name = horse_system(h, blood_type)
            target_systems = norm_val(r.get("最終対象系統", ""))
            if not sys_name or sys_name not in target_systems:
                continue

            conds = rule_conditions(r)
            ok_conds = []
            ng_conds = []
            for idx, item, content in conds:
                if match_value(h, item, content):
                    ok_conds.append(f"{item}={content}")
                else:
                    ng_conds.append(f"{item}={content}")

            if ng_conds:
                continue

            results.append({
                "判定": norm_val(course_row.get("判定")),
                "優先度": norm_val(course_row.get("優先度")),
                "日付": norm_val(h.get("日付", "")),
                "競馬場": course_key[0],
                "R": norm_val(h.get("R", "")),
                "レース名": norm_val(h.get("レース名", "")),
                "芝ダ": course_key[1],
                "距離": course_key[2],
                "馬番": norm_val(h.get("馬番", "")),
                "馬名": norm_val(h.get("馬名", "")),
                "血統区分": blood_type,
                "該当系統": sys_name,
                "採用項目数": len(conds),
                "一致条件": " / ".join(ok_conds),
                "検証複勝率%": norm_val(course_row.get("複勝率%", "")),
                "複勝回収率%": norm_val(course_row.get("複勝回収率%", "")),
                "リフト": norm_val(course_row.get("リフト", "")),
                "該当頭数_検証": norm_val(course_row.get("該当頭数", "")),
                "判定理由": norm_val(course_row.get("判定理由", "")),
            })

    out = pd.DataFrame(results)
    if not out.empty:
        # 同じ馬が父系・母父系両方で該当した場合は残す。並びだけ整える。
        sort_cols = [c for c in ["判定", "優先度", "競馬場", "R", "馬番"] if c in out.columns]
        out = out.sort_values(sort_cols).reset_index(drop=True)
    return out


# ファイル存在チェック
base = Path(".")
logic_path = base / LOGIC_FILE
course_path = base / COURSE_FILE

with st.sidebar:
    st.header("設定")
    use_statuses = st.multiselect(
        "使用するコース判定",
        ["採用", "保留", "除外"],
        default=["採用"],
        help="基本は採用のみ。候補を広げたい場合だけ保留を追加してください。",
    )
    show_sample = st.checkbox("必要列サンプルを表示", value=True)

if not logic_path.exists() or not course_path.exists():
    st.error("必要なCSVがapp.pyと同じ場所にありません。")
    st.write("同じ場所に置くCSV:")
    st.code(f"{LOGIC_FILE}\n{COURSE_FILE}")
    st.stop()

logic_df = read_csv_smart(logic_path)
course_df = read_csv_smart(course_path)

if show_sample:
    st.subheader("貼り付けCSVの必要列")
    st.code("日付,競馬場,R,レース名,芝ダ,距離,馬番,馬名,父タイプ名,母父タイプ名,性別,年齢,所属,斤量,頭数,天気,馬場状態,前芝・ダ,前距離,前走馬場状態,前走斤量,替,休み明け〜戦目")
    st.caption("前走所属がない場合は所属で代替します。馬体重増減は未使用です。")

csv_text = st.text_area("予想に必要な項目CSVを貼り付け", height=260, placeholder="ここにCSV本文を貼り付けてください")

col1, col2 = st.columns([1, 1])
with col1:
    run = st.button("鉄板⭐️候補を抽出", type="primary", use_container_width=True)
with col2:
    st.caption("iPhoneでは、下のCSV結果を長押し/全選択でコピーできます。")

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
            st.download_button("結果CSVをダウンロード", csv_out, file_name="teppan_bloodline_result.csv", mime="text/csv", use_container_width=True)
            st.subheader("コピー用CSV")
            st.code(csv_out, language="csv")
    except Exception as e:
        st.error("処理中にエラーが出ました。")
        st.exception(e)
