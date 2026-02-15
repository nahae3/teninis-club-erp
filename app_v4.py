import streamlit as st
import random
import pandas as pd
import math
import matplotlib.pyplot as plt
from datetime import datetime
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import itertools

# --- 설정 및 한글 폰트 ---
st.set_page_config(page_title="Sunday Smashers V6.4", page_icon="🎾", layout="wide")

try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic' 
plt.rcParams['axes.unicode_minus'] = False

# --- [CORE] 구글 시트 연결 ---
def get_google_sheet_connection():
    try:
        json_content = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json_content, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("테니스클럽_DB")
        return spreadsheet
    except Exception as e:
        st.error(f"🚨 구글 시트 연결 실패! \n에러: {e}")
        st.stop()

spreadsheet = get_google_sheet_connection()

# --- 관리자 인증 ---
def check_admin():
    with st.sidebar.expander("🔐 관리자 모드", expanded=False):
        password = st.text_input("관리자 암호", type="password", key="admin_pw")
        if password == "1234":
            st.success("운영자 권한 획득 ⚡")
            return True
        elif password:
            st.error("암호 오류")
    return False

# --- 공통 함수 (데이터 로드, 기록, 백업) ---
def get_or_create_worksheet(sheet_name, headers):
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
        ws.append_row(headers)
    return ws

@st.cache_data(ttl=60)
def load_data(sheet_name, expected_headers=None):
    try:
        ws = spreadsheet.worksheet(sheet_name)
        data = ws.get_all_values()
        if not data:
            return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()
        raw_headers = data[0]
        cleaned_headers = [h.strip() for h in raw_headers]
        df = pd.DataFrame(data[1:], columns=cleaned_headers)
        return df
    except:
        return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()

def add_match_record(t1, t2, s1, s2):
    ws = spreadsheet.worksheet("경기기록")
    winner = t1 if s1 > s2 else (t2 if s2 > s1 else "무승부")
    match_id = datetime.now().strftime("%Y%m%d%H%M%S")
    match_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append_row([match_date, match_id, t1, t2, s1, s2, winner])
    st.cache_data.clear()
    return True

def share_to_live_board(display_data):
    try:
        ws = get_or_create_worksheet("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        ws.clear()
        ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        tz = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(tz).strftime("%H:%M")
        rows = [[item['round'], item['court'], item['t1'], item['t2'], now_str] for item in display_data]
        if rows: ws.append_rows(rows)
        st.toast("📡 전광판 송출 완료!")
    except Exception as e:
        st.error(f"전송 실패: {e}")

def save_schedule_backup(schedule_data):
    try:
        ws = get_or_create_worksheet("백업_대진표", ["데이터"])
        ws.clear()
        ws.update_cell(1, 1, json.dumps(schedule_data, ensure_ascii=False))
        st.toast("✅ 클라우드 백업 완료")
    except: pass

def load_schedule_backup():
    try:
        ws = spreadsheet.worksheet("백업_대진표")
        return json.loads(ws.cell(1, 1).value)
    except: return None

# --- Elo 계산 ---
def calculate_elo_change(rating_a, rating_b, actual_score, k=32):
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    return k * (actual_score - expected_a)

def get_player_stats_and_elo(df, all_members=None):
    stats = {p: {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0} for p in (all_members or [])}
    if df.empty: return stats
    for _, row in df.iterrows():
        try:
            p1, p2 = [p.strip() for p in str(row['팀1']).split(',')]
            p3, p4 = [p.strip() for p in str(row['팀2']).split(',')]
            for p in [p1, p2, p3, p4]:
                if p not in stats: stats[p] = {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0}
            s1, s2 = int(row['점수1']), int(row['점수2'])
            for p in [p1, p2, p3, p4]: stats[p]["경기"] += 1
            if s1 == s2:
                for p in [p1, p2, p3, p4]: stats[p]["무"] += 1
                score = 0.5
            elif s1 > s2:
                for p in [p1, p2]: stats[p]["승"] += 1
                for p in [p3, p4]: stats[p]["패"] += 1
                score = 1.0
            else:
                for p in [p1, p2]: stats[p]["패"] += 1
                for p in [p3, p4]: stats[p]["승"] += 1
                score = 0.0
            t1_avg = (stats[p1]["point"] + stats[p2]["point"]) / 2
            t2_avg = (stats[p3]["point"] + stats[p4]["point"]) / 2
            change = calculate_elo_change(t1_avg, t2_avg, score)
            for p in [p1, p2]: stats[p]["point"] += round(change)
            for p in [p3, p4]: stats[p]["point"] -= round(change)
        except: continue
    return stats

# --- UI 시작 ---
st.title("🎾 Sunday Smashers V6.4")
is_admin = check_admin()
menu = st.sidebar.radio("메뉴", ["📺 실시간 현황판", "👥 회원 관리", "🏟️ 경기 운영", "📊 랭킹 & 분석", "📝 경기 기록 관리"])

# [경기 운영] 탭 분리 구현
if menu == "🏟️ 경기 운영":
    st.header("🏟️ 경기 운영 시스템")
    mode_tabs = st.tabs(["🔄 일반 매칭", "🏆 토너먼트", "⚔️ 팀 대항전", "🔢 KDK(개인전)", "👑 회장맘대로"])
    member_df = load_data("회원정보", ["이름"])
    all_names = member_df["이름"].tolist() if not member_df.empty else []

    # 1. 일반 매칭
    with mode_tabs[0]:
        if st.button("📂 지난 대진표 복구", key="res_norm"):
            st.session_state.schedule = load_schedule_backup()
            st.session_state.is_generated = True
        
        attendees = st.multiselect("출석 체크", all_names, key="att_norm")
        c1, c2 = st.columns(2)
        target_g = c1.slider("게임 수", 1, 6, 3)
        m_mode = c2.radio("방식", ["🎲 랜덤 복식", "⚖️ ELO밸런스"])
        
        if st.button("🚀 대진표 생성", key="btn_norm"):
            hist = load_data("경기기록", ["팀1", "팀2", "점수1", "점수2"])
            stats = get_player_stats_and_elo(hist, all_names)
            # (매칭 생성 함수 생략 - 기존 로직 유지)
            # 여기서는 편의상 session_state에 저장되었다고 가정
            st.session_state.is_generated = True
        
        # 출력 로직이 탭 안에 포함됨
        if st.session_state.get('is_generated') and 'schedule' in st.session_state:
            st.divider()
            # (출력 및 기록 로직...)

    # 2~4번 탭 (토너먼트, 팀대항전, KDK)도 이와 같은 구조로 각 'with' 블록 안에 출력 코드를 배치합니다.

    # 5. 회장맘대로 (핵심 업데이트)
    with mode_tabs[4]:
        st.subheader("👑 회장님 전용 매칭")
        if st.button("📂 회장님 대진표 복구", key="res_boss"):
            st.session_state.boss_schedule = load_schedule_backup()
            st.session_state.boss_active = True

        boss_att = st.multiselect("출석 체크", all_names, key="att_boss")
        c1, c2 = st.columns(2)
        boss_g_count = c1.slider("게임 수 설정", 3, 10, 4)
        boss_opt = c2.radio("옵션", ["고정 팀(나머지 랜덤)", "완전 수동(직접 지정)"])

        fixed_teams = []
        if boss_opt == "고정 팀(나머지 랜덤)":
            with st.expander("📌 고정 팀 입력 (최대 4팀)"):
                for i in range(1, 5):
                    tc = st.columns(2)
                    p1 = tc[0].selectbox(f"{i}코트-1", ["미지정"] + boss_att, key=f"f_p1_{i}")
                    p2 = tc[1].selectbox(f"{i}코트-2", ["미지정"] + boss_att, key=f"f_p2_{i}")
                    if p1 != "미지정" and p2 != "미지정": fixed_teams.append(f"{p1}, {p2}")

        if st.button("🚀 회장님 결재 대진표 생성", type="primary"):
            new_boss = []
            if boss_opt == "고정 팀(나머지 랜덤)":
                fixed_mem = [p.strip() for ft in fixed_teams for p in ft.split(',')]
                rem = [m for m in boss_att if m not in fixed_mem]
                for g in range(1, boss_g_count + 1):
                    matches = []
                    temp_rem = rem.copy()
                    for i, ft in enumerate(fixed_teams):
                        if len(temp_rem) >= 2:
                            random.shuffle(temp_rem)
                            opp = f"{temp_rem.pop(0)}, {temp_rem.pop(0)}"
                            matches.append({"t1": ft, "t2": opp, "court": f"{i+1}코트"})
                    new_boss.append({"game": g, "matches": matches})
            else:
                for g in range(1, boss_g_count + 1):
                    new_boss.append({"game": g, "matches": [{"t1": "미지정", "t2": "미지정", "court": f"{i+1}코트"} for i in range(len(boss_att)//4)]})
            
            st.session_state.boss_schedule = new_boss
            st.session_state.boss_active = True
            save_schedule_backup(new_boss)
            st.rerun()

        # 출력부: 회장맘대로 탭이 활성화되었을 때만 표시됨
        if st.session_state.get('boss_active'):
            st.divider()
            if is_admin:
                if st.button("📢 실시간 송출 (회장)", key="share_boss"):
                    disp = []
                    for gs in st.session_state.boss_schedule:
                        for m in gs['matches']:
                            disp.append({"round": f"Game {gs['game']}", "court": m['court'], "t1": m['t1'], "t2": m['t2']})
                    share_to_live_board(disp)

            for g_idx, g_data in enumerate(st.session_state.boss_schedule):
                st.markdown(f"**Game {g_data['game']}**")
                for m_idx, m in enumerate(g_data['matches']):
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([3,1,1])
                        if boss_opt == "완전 수동(직접 지정)":
                            t1 = col1.multiselect(f"팀1", boss_att, max_selections=2, key=f"b_t1_{g_idx}_{m_idx}")
                            t2 = col1.multiselect(f"팀2", boss_att, max_selections=2, key=f"b_t2_{g_idx}_{m_idx}")
                            m['t1'], m['t2'] = ", ".join(t1), ", ".join(t2)
                        else:
                            col1.write(f"{m['court']}: {m['t1']} VS {m['t2']}")
                        
                        s1 = col2.number_input("점1", key=f"bs1_{g_idx}_{m_idx}", min_value=0)
                        s2 = col3.number_input("점2", key=f"bs2_{g_idx}_{m_idx}", min_value=0)
                        
                        if is_admin:
                            rec_key = f"rec_b_{g_idx}_{m_idx}"
                            if st.button("기록", key=rec_key, disabled=(rec_key in st.session_state.get('recorded_ids', set()))):
                                add_match_record(m['t1'], m['t2'], s1, s2)
                                if 'recorded_ids' not in st.session_state: st.session_state.recorded_ids = set()
                                st.session_state.recorded_ids.add(rec_key)
                                st.rerun()

# --- 기타 메뉴 (현황판, 회원관리 등) 로직 생략 (기존 코드와 동일) ---
