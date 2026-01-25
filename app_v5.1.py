import streamlit as st
import random
import pandas as pd
import math
import matplotlib.pyplot as plt
from datetime import datetime
import pytz # 시간 처리를 위해 추가
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- 설정 및 한글 폰트 ---
st.set_page_config(page_title="행님표 테니스 ERP V5.1 (Live 공유)", page_icon="🎾", layout="wide")

# [폰트 설정]
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic' 
plt.rcParams['axes.unicode_minus'] = False

# --- [CORE] 구글 시트 연결 설정 ---
def get_google_sheet_connection():
    try:
        json_content = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json_content, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("테니스클럽_DB")
        return spreadsheet
    except Exception as e:
        st.error(f"🚨 구글 시트 연결 실패! Secrets 설정과 시트 이름을 확인하세요.\n에러: {e}")
        st.stop()

spreadsheet = get_google_sheet_connection()

# --- 데이터 관리 함수 ---

def get_or_create_worksheet(sheet_name, headers):
    """시트를 가져오거나 없으면 생성"""
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
        ws.append_row(headers)
    return ws

@st.cache_data(ttl=60)
def load_data(sheet_name, expected_headers):
    """데이터 로드"""
    try:
        ws = get_or_create_worksheet(sheet_name, expected_headers)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame(columns=expected_headers)
        for col in df.columns:
            df[col] = df[col].astype(str)
        if '점수1' in df.columns: df['점수1'] = pd.to_numeric(df['점수1'], errors='coerce').fillna(0).astype(int)
        if '점수2' in df.columns: df['점수2'] = pd.to_numeric(df['점수2'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류: {e}")
        return pd.DataFrame(columns=expected_headers)

def add_member_to_db(name, memo):
    """회원 추가"""
    ws = spreadsheet.worksheet("회원정보")
    join_date = datetime.now().strftime("%Y-%m-%d")
    ws.append_row([name, join_date, memo])
    st.cache_data.clear()

def add_match_record(t1, t2, s1, s2):
    """경기 기록 추가"""
    ws = spreadsheet.worksheet("경기기록")
    winner = t1 if s1 > s2 else (t2 if s2 > s1 else "무승부")
    match_id = datetime.now().strftime("%Y%m%d%H%M%S")
    match_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append_row([match_date, match_id, t1, t2, s1, s2, winner])
    st.cache_data.clear()
    return True

def delete_match_records(match_ids_to_delete):
    """경기 기록 삭제"""
    ws = spreadsheet.worksheet("경기기록")
    all_records = ws.get_all_records()
    df = pd.DataFrame(all_records)
    df['경기ID'] = df['경기ID'].astype(str)
    match_ids_str = [str(x) for x in match_ids_to_delete]
    new_df = df[~df['경기ID'].isin(match_ids_str)]
    ws.clear()
    ws.update([new_df.columns.values.tolist()] + new_df.values.tolist())
    st.cache_data.clear()

# --- [NEW] 실시간 공유 기능 (Live) ---
def share_live_schedule_to_db(schedule_list):
    """생성된 일반 매칭 스케줄을 '실시간현황' 시트에 저장"""
    try:
        ws = get_or_create_worksheet("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        ws.clear() # 기존 내용 삭제
        
        # 헤더 다시 쓰기
        ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        
        # 한국 시간
        tz = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(tz).strftime("%H:%M")
        
        rows_to_add = []
        for round_data in schedule_list:
            r_num = round_data['round_num']
            for idx, match in enumerate(round_data['matches']):
                rows_to_add.append([
                    f"Round {r_num}",
                    f"{idx + 1}코트",
                    match['t1'],
                    match['t2'],
                    now_str
                ])
        
        if rows_to_add:
            ws.append_rows(rows_to_add)
            st.toast("📢 대진표 공유 완료! (실시간현황 탭)", icon="✅")
        else:
            st.warning("공유할 대진표 내용이 없습니다.")
            
    except Exception as e:
        st.error(f"공유 실패: {e}")

def load_live_status():
    """실시간 현황 불러오기"""
    return load_data("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])

# --- Elo 및 알고리즘 (기존 유지) ---
def calculate_elo_change(rating_a, rating_b, actual_score, k=32):
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    change = k * (actual_score - expected_a)
    return change

def get_player_stats_and_elo(df, all_members=None):
    stats = {}
    if all_members:
        for p in all_members:
            stats[p] = {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0}
    if df.empty: return stats
    if '날짜' in df.columns: df = df.sort_values("날짜")

    for _, row in df.iterrows():
        try:
            p1, p2 = [p.strip() for p in str(row['팀1']).split(',')]
            p3, p4 = [p.strip() for p in str(row['팀2']).split(',')]
            winner = row['승리팀']
            for p in [p1, p2, p3, p4]:
                if p not in stats: stats[p] = {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0}
            for p in [p1, p2, p3, p4]: stats[p]["경기"] += 1
            if winner == "무승부":
                for p in [p1, p2, p3, p4]: stats[p]["무"] += 1
                continue 
            is_team1_win = (winner == row['팀1'])
            if is_team1_win:
                for p in [p1, p2]: stats[p]["승"] += 1
                for p in [p3, p4]: stats[p]["패"] += 1
            else:
                for p in [p1, p2]: stats[p]["패"] += 1
                for p in [p3, p4]: stats[p]["승"] += 1
            team1_avg = (stats[p1]["point"] + stats[p2]["point"]) / 2
            team2_avg = (stats[p3]["point"] + stats[p4]["point"]) / 2
            actual_score = 1 if is_team1_win else 0
            change = calculate_elo_change(team1_avg, team2_avg, actual_score)
            for p in [p1, p2]: stats[p]["point"] += round(change)
            for p in [p3, p4]: stats[p]["point"] -= round(change)
        except: continue
    return stats

def balance_teams_by_point(players, stats):
    sorted_p = sorted(players, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
    team_a, team_b = [], []
    for i, p in enumerate(sorted_p):
        if i % 4 in [0, 3]: team_a.append(p)
        else: team_b.append(p)
    return team_a, team_b

def generate_league_schedule(attendees, target_games, mode, stats):
    schedule = []
    play_counts = {p: 0 for p in attendees}
    courts_num = len(attendees) // 4
    if courts_num == 0: return []
    total_slots_needed = len(attendees) * target_games
    slots_per_round = courts_num * 4
    total_rounds = math.ceil(total_slots_needed / slots_per_round)
    
    for r in range(total_rounds):
        waiting_list = sorted(attendees, key=lambda x: (play_counts[x], random.random()))*_
