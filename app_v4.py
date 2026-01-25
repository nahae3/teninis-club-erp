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

# --- 설정 및 한글 폰트 ---
st.set_page_config(page_title="행님표 테니스 ERP V5.2", page_icon="🎾", layout="wide")

# [폰트 설정]
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
        st.error(f"🚨 구글 시트 연결 실패! Secrets 설정과 시트 이름을 확인하세요.\n에러: {e}")
        st.stop()

spreadsheet = get_google_sheet_connection()

# --- [NEW] 관리자 인증 함수 ---
def check_admin():
    """사이드바에서 비밀번호를 입력받아 관리자 여부 확인"""
    with st.sidebar.expander("🔐 관리자 모드", expanded=False):
        password = st.text_input("관리자 암호", type="password", key="admin_pw")
        if password == "1234":  # [설정] 비밀번호 변경은 여기서
            st.success("운영자 권한 획득 ⚡")
            return True
        elif password:
            st.error("암호 오류")
    return False

# --- 데이터 관리 함수 ---
def get_or_create_worksheet(sheet_name, headers):
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
        ws.append_row(headers)
    return ws

@st.cache_data(ttl=60)
# [데이터 로드 함수 - 강력한 버전]
# 헤더에 공백이 있거나("점수1 "), 실수로 띄어쓰기("점수 1")를 해도 다 알아서 찾아줍니다.
def load_data(sheet_name, expected_headers=None):
    try:
        ws = spreadsheet.worksheet(sheet_name)
        data = ws.get_all_values() # 데이터를 있는 그대로 텍스트로 다 가져옴
        
        if not data:
            return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()
        
        # 1. 엑셀의 헤더(첫 줄)를 가져와서 앞뒤 공백을 싹 제거함
        # 예: " 점수1 " -> "점수1"
        raw_headers = data[0]
        cleaned_headers = [h.strip() for h in raw_headers]
        
        # 2. 데이터 프레임 생성
        df = pd.DataFrame(data[1:], columns=cleaned_headers)
        
        # 3. 요청한 컬럼만 골라내기 (없으면 0으로 채움)
        if expected_headers:
            final_df = pd.DataFrame()
            for col in expected_headers:
                clean_col = col.strip() # 요청한 컬럼명도 공백 제거
                
                # 정확히 일치하는게 있으면 가져오고
                if clean_col in df.columns:
                    final_df[col] = df[clean_col]
                # 혹시 "점수 1" 처럼 중간 공백 차이일 수도 있으니 한번 더 찾기
                else:
                    found = False
                    for h in df.columns:
                        if h.replace(" ","") == clean_col.replace(" ",""):
                            final_df[col] = df[h]
                            found = True
                            break
                    if not found:
                        final_df[col] = 0 # 진짜 없으면 0 처리
            return final_df
        
        return df
    except Exception as e:
        return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()


def add_member_to_db(name, memo):
    ws = spreadsheet.worksheet("회원정보")
    join_date = datetime.now().strftime("%Y-%m-%d")
    ws.append_row([name, join_date, memo])
    st.cache_data.clear()

def add_match_record(t1, t2, s1, s2):
    ws = spreadsheet.worksheet("경기기록")
    winner = t1 if s1 > s2 else (t2 if s2 > s1 else "무승부")
    match_id = datetime.now().strftime("%Y%m%d%H%M%S")
    match_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append_row([match_date, match_id, t1, t2, s1, s2, winner])
    st.cache_data.clear()
    return True

def delete_match_records(match_ids_to_delete):
    ws = spreadsheet.worksheet("경기기록")
    all_records = ws.get_all_records()
    df = pd.DataFrame(all_records)
    df['경기ID'] = df['경기ID'].astype(str)
    match_ids_str = [str(x) for x in match_ids_to_delete]
    new_df = df[~df['경기ID'].isin(match_ids_str)]
    ws.clear()
    ws.update([new_df.columns.values.tolist()] + new_df.values.tolist())
    st.cache_data.clear()

# --- [UPGRADE] 통합 실시간 공유 함수 ---
def share_to_live_board(display_data):
    """
    display_data 형식:
    [
      {"round": "4강", "court": "1코트", "t1": "김철수,이영희", "t2": "박민수,최수지"},
      ...
    ]
    """
    try:
        ws = get_or_create_worksheet("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        ws.clear()
        ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        
        tz = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(tz).strftime("%H:%M")
        
        rows = []
        for item in display_data:
            rows.append([item['round'], item['court'], item['t1'], item['t2'], now_str])
            
        if rows:
            ws.append_rows(rows)
            st.toast("📢 실시간 전광판 송출 완료!", icon="📡")
        else:
            st.warning("송출할 데이터가 없습니다.")
    except Exception as e:
        st.error(f"전송 실패: {e}")

def load_live_status():
    return load_data("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])

# --- Elo 및 알고리즘 ---
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
        waiting_list = sorted(attendees, key=lambda x: (play_counts[x], random.random()))
        players_for_round = waiting_list[:slots_per_round]
        matches = []
        if mode == "🎲 랜덤 복식":
            random.shuffle(players_for_round)
            for i in range(len(players_for_round)//4):
                matches.append({"t1": f"{players_for_round[i*4]}, {players_for_round[i*4+1]}", "t2": f"{players_for_round[i*4+2]}, {players_for_round[i*4+3]}"})
        else:
            sorted_p = sorted(players_for_round, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
            n = len(sorted_p)
            for i in range(n // 4):
                matches.append({"t1": f"{sorted_p[i]}, {sorted_p[n-1-i]}", "t2": f"{sorted_p[i+1]}, {sorted_p[n-2-i]}"})
        schedule.append({"round_num": r + 1, "matches": matches})
        for p in players_for_round: play_counts[p] += 1
    return schedule

def generate_kdk_schedule(players, rounds):
    n = len(players)
    schedule = []
    idxs = list(range(n))
    for r in range(rounds):
        matches = []
        random.shuffle(idxs)
        for i in range(n // 4):
            base = i * 4
            if base + 3 < n:
                p1, p2 = players[idxs[base]], players[idxs[base+1]]
                p3, p4 = players[idxs[base+2]], players[idxs[base+3]]
                matches.append({"t1": f"{p1}, {p2}", "t2": f"{p3}, {p4}", "done": False})
        schedule.append({"round": r+1, "matches": matches})
    return schedule

def draw_bracket_plot(teams_4):
    winners = st.session_state.get('tourney_winners', {})
    semi_1_t1, semi_1_t2 = teams_4[0], teams_4[1]
    semi_2_t1, semi_2_t2 = teams_4[2], teams_4[3]
    final_1 = winners.get('semi_1', '???')
    final_2 = winners.get('semi_2', '???')
    champion = winners.get('final', '최종 우승') 

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis('off')
    # ... (그림 그리기 로직 생략, 기존과 동일) ...
    # 코드 길이상 핵심 로직 유지
    x_semi, x_final, x_winner = 0.2, 0.5, 0.8
    y_s1_top, y_s1_bot = 0.8, 0.6
    y_s2_top, y_s2_bot = 0.4, 0.2
    y_f1, y_f2, y_win = 0.7, 0.3, 0.5
    
    def draw_box(x, y, text, color='#f0f2f6', highlight=False):
        ec = 'gold' if highlight else 'black'
        lw = 2 if highlight else 1
        fc = 'gold' if highlight else color
        ax.text(x, y, text, ha='center', va='center', fontsize=9, bbox=dict(boxstyle="round,pad=0.3", facecolor=fc, edgecolor=ec, linewidth=lw))
    
    draw_box(x_semi, y_s1_top, semi_1_t1, highlight=(semi_1_t1==final_1))
    draw_box(x_semi, y_s1_bot, semi_1_t2, highlight=(semi_1_t2==final_1))
    draw_box(x_semi, y_s2_top, semi_2_t1, highlight=(semi_2_t1==final_2))
    draw_box(x_semi, y_s2_bot, semi_2_t2, highlight=(semi_2_t2==final_2))
    draw_box(x_final, y_f1, f"{final_1}", color='lightblue', highlight=(final_1==champion))
    draw_box(x_final, y_f2, f"{final_2}", color='lightblue', highlight=(final_2==champion))
    draw_box(x_winner, y_win, champion, color='gold', highlight=(champion!='최종 우승'))
    
    ax.plot([x_semi, x_final], [y_s1_top, y_f1], color='gray', alpha=0.3)
    ax.plot([x_semi, x_final], [y_s1_bot, y_f1], color='gray', alpha=0.3)
    ax.plot([x_semi, x_final], [y_s2_top, y_f2], color='gray', alpha=0.3)
    ax.plot([x_semi, x_final], [y_s2_bot, y_f2], color='gray', alpha=0.3)
    ax.plot([x_final, x_winner], [y_f1, y_win], color='black', alpha=0.5)
    ax.plot([x_final, x_winner], [y_f2, y_win], color='black', alpha=0.5)
    return fig

# --- UI 시작 ---
st.title("🎾 가칭:행님들 테니스 V5.2")

# 인증 확인 (관리자 모드 활성화 여부)
is_admin = check_admin()

menu = st.sidebar.radio("메뉴", ["📺 실시간 현황판", "👥 회원 관리", "🏟️ 경기 운영", "📊 Elo 랭킹 & 분석", "📝 경기 기록 관리"])

# --- [NEW] 관리자용 데이터 백업 버튼 (사이드바) ---
if is_admin:
    st.sidebar.divider()
    st.sidebar.markdown("💾 **데이터 백업**")
    
    # 경기 기록 다운로드
    hist_df = load_data("경기기록", ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
    csv = hist_df.to_csv(index=False).encode('utf-8-sig') # 한글 깨짐 방지
    
    st.sidebar.download_button(
        label="📥 경기기록 다운로드 (CSV)",
        data=csv,
        file_name=f"경기기록_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


# [0] 실시간 현황판 (누구나 접속 가능 + 관리자용 초기화 버튼)
if menu == "📺 실시간 현황판":
    st.header("📺 LIVE SCOREBOARD")
    
    # [NEW] 관리자 전용: 영업 종료 버튼
    if is_admin:
        col_adm1, col_adm2 = st.columns([1, 1])
        with col_adm1:
            if st.button("🚫 현황판 초기화 (일정 종료)", type="primary", use_container_width=True):
                try:
                    ws = spreadsheet.worksheet("실시간현황")
                    ws.clear()
                    ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"]) # 헤더만 남김
                    st.toast("현황판을 초기화했습니다. (영업 종료)", icon="👋")
                    st.rerun()
                except Exception as e:
                    st.error(f"초기화 실패: {e}")
        with col_adm2:
            if st.button("🔄 새로고침", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
    else:
        # 일반 회원은 새로고침 버튼만
        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
    live_df = load_live_status()
    
    # 데이터가 있고, 내용이 비어있지 않은 경우에만 표시
    if not live_df.empty and len(live_df) > 0 and live_df.iloc[0]['팀1'] != "": 
        last_update = live_df['업데이트시간'].iloc[0] if '업데이트시간' in live_df.columns else "?"
        st.caption(f"🕒 Update: {last_update}")
        rounds = live_df['라운드'].unique()
        for r in rounds:
            st.subheader(f"📌 {r}")
            r_data = live_df[live_df['라운드'] == r]
            for _, row in r_data.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([1, 0.2, 1])
                    with col1: st.markdown(f"<div style='text-align:center; color:blue; font-weight:bold;'>{row['팀1']}</div>", unsafe_allow_html=True)
                    with col2: st.markdown(f"<div style='text-align:center;'>VS</div>", unsafe_allow_html=True)
                    with col3: st.markdown(f"<div style='text-align:center; color:red; font-weight:bold;'>{row['팀2']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align:center; font-size:0.8em; color:gray;'>🏟️ {row['코트']}</div>", unsafe_allow_html=True)
    else:
        st.info("현재 진행 중인 경기가 없습니다. (일정 종료)")
        st.caption("운영자가 대진표를 공유하면 여기에 표시됩니다.")


# [1] 회원 관리 (수정버전: 삭제 기능 추가)
elif menu == "👥 회원 관리":
    st.header("👥 회원 관리")
    
    # 데이터 로드
    member_df = load_data("회원정보", ["이름", "가입일", "메모"])
    
    tab1, tab2 = st.tabs(["📜 회원 목록", "⚙️ 관리 (등록/삭제)"])
    
    with tab1:
        st.dataframe(member_df, width="stretch", hide_index=True)
        st.caption(f"총 회원수: {len(member_df)}명")
        
    with tab2:
        if is_admin:
            c1, c2 = st.columns(2)
            
            # [등록]
            with c1:
                st.subheader("➕ 신규 회원 등록")
                with st.form("add_member_form"):
                    name = st.text_input("이름")
                    memo = st.text_input("메모 (선택)")
                    if st.form_submit_button("등록"):
                        if name and name not in member_df["이름"].values:
                            add_member_to_db(name, memo)
                            st.success(f"'{name}' 회원 등록 완료!")
                            st.rerun()
                        elif name in member_df["이름"].values:
                            st.error("이미 등록된 이름입니다.")
                        else:
                            st.error("이름을 입력하세요.")
                            
            # [삭제] - 새로 추가된 기능
            with c2:
                st.subheader("🗑️ 회원 삭제")
                if not member_df.empty:
                    to_delete = st.selectbox("삭제할 회원 선택", member_df["이름"].tolist())
                    
                    st.warning("⚠️ 삭제하면 복구할 수 없습니다.")
                    if st.button("선택한 회원 영구 삭제", type="primary"):
                        try:
                            ws = spreadsheet.worksheet("회원정보")
                            # 이름이 있는 셀 찾기
                            cell = ws.find(to_delete)
                            ws.delete_rows(cell.row)
                            st.cache_data.clear()
                            st.success(f"'{to_delete}' 님을 명단에서 삭제했습니다.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"삭제 중 오류 발생: {e}")
                else:
                    st.info("삭제할 회원이 없습니다.")
        else:
            st.info("🔒 회원 등록 및 삭제는 관리자 권한이 필요합니다.")
            st.caption("사이드바에서 관리자 암호를 입력하세요.")


# [2] 경기 운영
elif menu == "🏟️ 경기 운영":
    st.header("🏟️ 경기 운영 시스템")
    mode_tab1, mode_tab2, mode_tab3, mode_tab4 = st.tabs(["🔄 일반 매칭", "🏆 토너먼트", "⚔️ 팀 대항전", "🔢 KDK"])
    member_df = load_data("회원정보", ["이름"])
    
    # 2.1 일반 매칭
    with mode_tab1:
        if not member_df.empty:
            attendees = st.multiselect("출석 체크", member_df["이름"].tolist(), key="league_att")
            c1, c2 = st.columns(2)
            with c1: target_games = st.slider("인당 게임 수", 1, 6, 3)
            with c2: match_mode = st.radio("방식", ["🎲 랜덤", "⚖️ AI밸런스"], horizontal=True, key="league_mode")
            
            # 생성 버튼 (누구나 눌러볼 수는 있게 함, 저장은 관리자)
            if st.button("🚀 대진표 생성", type="primary"):
                hist = load_data("경기기록", ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
                stats = get_player_stats_and_elo(hist, member_df["이름"].tolist())
                st.session_state.schedule = generate_league_schedule(attendees, target_games, match_mode, stats)
                st.session_state.is_generated = True
                st.session_state.recorded_ids = set() # [NEW] 기록된 매치 추적용

            if st.session_state.get('is_generated'):
                st.divider()
                # [공유 기능] 관리자만 가능
                if is_admin:
                    if st.button("📢 실시간 중계하기 (일반)", use_container_width=True):
                        display_data = []
                        for rd in st.session_state.schedule:
                            for idx, m in enumerate(rd['matches']):
                                display_data.append({"round": f"Round {rd['round_num']}", "court": f"{idx+1}코트", "t1": m['t1'], "t2": m['t2']})
                        share_to_live_board(display_data)

                for round_data in st.session_state.schedule:
                    r_num = round_data['round_num']
                    st.markdown(f"**Round {r_num}**")
                    for idx, match in enumerate(round_data['matches']):
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([2,1,1])
                            c1.caption(f"{match['t1']} vs {match['t2']}")
                            # [NEW] max_value 제거
                            s1 = c2.number_input("점1", key=f"r{r_num}m{idx}s1", min_value=0) 
                            s2 = c3.number_input("점2", key=f"r{r_num}m{idx}s2", min_value=0)
                            
                            unique_key = f"btn_r{r_num}m{idx}"
                            is_done = unique_key in st.session_state.get('recorded_ids', set())
                            
                            if is_admin:
                                # [NEW] disabled 속성 추가
                                if st.button("기록" if not is_done else "완료됨", key=unique_key, disabled=is_done):
                                    add_match_record(match['t1'], match['t2'], s1, s2)
                                    st.session_state.recorded_ids.add(unique_key)
                                    st.toast("기록 저장 완료!")
                                    st.rerun()
                            elif not is_admin and not is_done:
                                st.caption("🔒 기록 권한 없음")

    # 2.2 토너먼트
    with mode_tab2:
        # (생략된 설정 UI는 위와 동일, 핵심 로직만 변경)
        if not member_df.empty:
            t_attendees = st.multiselect("참가 선수", member_df["이름"].tolist(), key="tourney_att")
            c1, c2 = st.columns(2)
            with c1: team_cnt = st.selectbox("팀 수", [4, 5, 6, 7, 8])
            with c2: team_method = st.selectbox("방식", ["⚖️ AI밸런스", "🎲 랜덤", "👆 수동"])
            
            # ... (수동 팀 설정 로직) ...
            manual_teams = [] # (간소화)
            
            if st.button("🏟️ 대회 시작", key="start_tourney"):
                # ... (팀 생성 로직 동일) ...
                final_teams = [f"팀{i}" for i in range(team_cnt)] # 임시
                if team_method == "🎲 랜덤":
                    random.shuffle(t_attendees)
                    final_teams = [f"{t_attendees[i*2]}, {t_attendees[i*2+1]}" for i in range(team_cnt)]
                # ... (Elo 로직 등) ...
                
                st.session_state.tourney_teams = final_teams
                st.session_state.tourney_winners = {}
                st.session_state.tourney_active = True
                st.session_state.tourney_step = "PRE" if team_cnt > 4 else "SF"
                st.session_state.matches_needed = team_cnt - 4
                st.rerun()

            if st.session_state.get('tourney_active'):
                teams = st.session_state.tourney_teams
                winners = st.session_state.get('tourney_winners', {})
                step = st.session_state.get('tourney_step')
                
                # [공유 기능] - 현재 단계에 맞춰 공유
                if is_admin:
                    if st.button("📢 실시간 중계하기 (토너먼트)", use_container_width=True):
                        display_data = []
                        if step == "PRE":
                            for i in range(st.session_state.matches_needed):
                                display_data.append({"round": "예선", "court": f"{i+1}코트", "t1": teams[i*2], "t2": teams[i*2+1]})
                        elif step == "SF":
                            sf_teams = st.session_state.get('sf_teams', teams)
                            display_data.append({"round": "4강", "court": "A코트", "t1": sf_teams[0], "t2": sf_teams[1]})
                            display_data.append({"round": "4강", "court": "B코트", "t1": sf_teams[2], "t2": sf_teams[3]})
                        share_to_live_board(display_data)

                # ... (경기 진행 로직) ...
                # max_value 제거 및 is_admin 체크 추가
                if step == "PRE":
                    cols = st.columns(4)
                    n_matches = st.session_state.matches_needed
                    all_done = True
                    for i in range(n_matches):
                        t1, t2 = teams[i*2], teams[i*2+1]
                        key = f"PRE_{i}"
                        with cols[i]:
                            st.caption(f"{t1} vs {t2}")
                            if key not in winners:
                                all_done = False
                                s1 = st.number_input("점1", key=f"pre_s1_{i}", min_value=0)
                                s2 = st.number_input("점2", key=f"pre_s2_{i}", min_value=0)
                                if is_admin:
                                    if st.button("입력", key=f"pre_btn_{i}"):
                                        winners[key] = t1 if s1 > s2 else t2
                                        add_match_record(t1, t2, s1, s2)
                                        st.rerun()
                            else: st.success(f"승: {winners[key]}")
                    if all_done and is_admin:
                         if st.button("🚀 4강 대진표 생성"):
                            st.session_state.sf_teams = list(winners.values()) + teams[n_matches*2:]
                            st.session_state.tourney_step = "SF"; st.rerun()

                elif step == "SF":
                    sf_teams = st.session_state.get('sf_teams', teams)
                    st.pyplot(draw_bracket_plot(sf_teams))
                    # 4강 입력 로직 (is_admin 적용)
                    c1, c2 = st.columns(2)
                    for i, loc in enumerate(['semi_1', 'semi_2']):
                         with [c1, c2][i]:
                            t1, t2 = sf_teams[i*2], sf_teams[i*2+1]
                            if loc not in winners:
                                s1 = st.number_input("점1", key=f"sf_s1_{i}", min_value=0)
                                s2 = st.number_input("점2", key=f"sf_s2_{i}", min_value=0)
                                if is_admin and st.button("입력", key=f"sf_btn_{i}"):
                                    winners[loc] = t1 if s1 > s2 else t2
                                    add_match_record(t1, t2, s1, s2)
                                    st.rerun()
                    # 결승 입력 로직 (is_admin 적용)
                    if 'semi_1' in winners and 'semi_2' in winners:
                        st.markdown(f"### 결승: {winners['semi_1']} vs {winners['semi_2']}")
                        if 'final' not in winners:
                            s1 = st.number_input("점1", key="fin_s1", min_value=0)
                            s2 = st.number_input("점2", key="fin_s2", min_value=0)
                            if is_admin and st.button("우승 확정", key="fin_btn"):
                                winners['final'] = winners['semi_1'] if s1 > s2 else winners['semi_2']
                                add_match_record(winners['semi_1'], winners['semi_2'], s1, s2)
                                st.balloons(); st.rerun()

    # 2.3 팀 대항전
    with mode_tab3:
        # ... (설정 UI 생략) ...
        if not member_df.empty:
            att_battle = st.multiselect("참석자", member_df["이름"].tolist(), key="battle_att")
            c1, c2 = st.columns(2)
            with c1: battle_mode = st.radio("팀 구성 방식", ["⚖️ AI밸런스", "👆 수동"], key="bt_mode")
            with c2: game_count = st.slider("총 경기 수", 3, 9, 5, step=2)
            
            # (수동 팀 설정 생략)
            manual_A, manual_B = [], []

            if st.button("⚖️ 시작"):
                # (팀 나누기 로직)
                ta, tb = [], []
                if battle_mode == "⚖️ Elo":
                     hist = load_data("경기기록", ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
                     stats = get_player_stats_and_elo(hist, member_df["이름"].tolist())
                     ta, tb = balance_teams_by_point(att_battle, stats)
                else: ta, tb = att_battle[:len(att_battle)//2], att_battle[len(att_battle)//2:] # 임시

                st.session_state.battle_teams = {'A': ta, 'B': tb}
                st.session_state.battle_active = True
                matches = []
                for i in range(game_count):
                    p1a, p2a = ta[(i*2)%len(ta)], ta[(i*2+1)%len(ta)]
                    p1b, p2b = tb[(i*2)%len(tb)], tb[(i*2+1)%len(tb)]
                    matches.append({"t1": f"{p1a}, {p2a}", "t2": f"{p1b}, {p2b}", "done": False})
                st.session_state.battle_matches = matches
            
            if st.session_state.get('battle_active'):
                matches = st.session_state.battle_matches
                ta, tb = st.session_state.battle_teams['A'], st.session_state.battle_teams['B']
                
                if is_admin:
                    if st.button("📢 실시간 중계하기 (팀전)", use_container_width=True):
                        display_data = []
                        for i, m in enumerate(matches):
                            if not m['done']:
                                display_data.append({"round": f"Game {i+1}", "court": "센터코트", "t1": m['t1'], "t2": m['t2']})
                        share_to_live_board(display_data)

                # 점수판
                score_a = sum(1 for m in matches if m.get('winner') == 'A')
                score_b = sum(1 for m in matches if m.get('winner') == 'B')
                st.markdown(f"### 🔵 A팀 {score_a} : {score_b} B팀 🔴")
                
                for i, m in enumerate(matches):
                    with st.expander(f"Game {i+1}", expanded=not m['done']):
                        if not m['done']:
                            c1, c2, c3 = st.columns([2, 0.5, 2])
                            # (선수 교체 UI 생략 - 기존 유지)
                            s1, s2 = st.columns(2)
                            sc1 = s1.number_input("A", key=f"ba_s1_{i}", min_value=0)
                            sc2 = s2.number_input("B", key=f"ba_s2_{i}", min_value=0)
                            if is_admin and st.button("결과 저장", key=f"ba_btn_{i}"):
                                m['winner'] = 'A' if sc1 > sc2 else 'B'
                                m['done'] = True
                                add_match_record(m['t1'], m['t2'], sc1, sc2)
                                st.rerun()
                        else: st.info(f"{m['winner']}팀 승리!")

    # 2.4 KDK
    with mode_tab4:
        # (기존 설정 로직)
        if not member_df.empty:
            kdk_att = st.multiselect("참가자", member_df["이름"].tolist(), key="kdk_att")
            kdk_rounds = st.slider("라운드", 1, 6, 4, key="kdk_rds")

            if st.button("🎲 대진표 생성"):
                st.session_state.kdk_schedule = generate_kdk_schedule(kdk_att, kdk_rounds)
                st.session_state.kdk_scores = {}
                st.session_state.kdk_active = True
                st.session_state.kdk_recorded = set()
                st.rerun()
            
            if st.session_state.get('kdk_active'):
                if is_admin:
                    if st.button("📢 실시간 중계하기 (KDK)", use_container_width=True):
                        display_data = []
                        for r in st.session_state.kdk_schedule:
                            for idx, m in enumerate(r['matches']):
                                key = f"kdk_r{r['round']}_m{idx}"
                                if key not in st.session_state.get('kdk_scores', {}):
                                    display_data.append({"round": f"R{r['round']}", "court": f"{idx+1}코트", "t1": m['t1'], "t2": m['t2']})
                        share_to_live_board(display_data)

                schedule = st.session_state.kdk_schedule
                scores = st.session_state.get('kdk_scores', {})
                
                # 랭킹 표시는 기존 유지 (생략)
                
                for r in schedule:
                    with st.expander(f"Round {r['round']}", expanded=True):
                        cols = st.columns(len(r['matches']))
                        for idx, m in enumerate(r['matches']):
                            key = f"kdk_r{r['round']}_m{idx}"
                            is_done = key in scores
                            
                            with cols[idx]:
                                st.caption(f"{m['t1']} vs {m['t2']}")
                                if not is_done:
                                    s1 = st.number_input("점1", key=f"k_s1_{key}", min_value=0)
                                    s2 = st.number_input("점2", key=f"k_s2_{key}", min_value=0)
                                    if is_admin and st.button("입력", key=f"k_btn_{key}"):
                                        scores[key] = {'s1': s1, 's2': s2, 'done': True}
                                        add_match_record(m['t1'], m['t2'], s1, s2)
                                        st.rerun()
                                else:
                                    st.success(f"{scores[key]['s1']} : {scores[key]['s2']}")

# [3] Elo 랭킹 & 분석
elif menu == "📊 Elo 랭킹 & 분석":
    st.header("🏆 랭킹 & 분석")
    
    # 데이터 로드 (이제 점수를 제대로 가져옴!)
    member_df = load_data("회원정보", ["이름"])
    df = load_data("경기기록", ["날짜", "승리팀", "팀1", "팀2", "점수1", "점수2"])
    
    if not df.empty:
        # 2. 전체 통계 계산
        stats = get_player_stats_and_elo(df, member_df["이름"].tolist())
        
        # 3. 랭킹 테이블
        rank_data = []
        for p, d in stats.items():
            if d['경기'] > 0:
                win_rate = (d['승'] / d['경기']) * 100
                rank_data.append({
                    "이름": p, 
                    "포인트": d['point'], 
                    "경기수": d['경기'], 
                    "승": d['승'], 
                    "패": d['패'], 
                    "승률": f"{win_rate:.1f}%"
                })
        
        rank_df = pd.DataFrame(rank_data).sort_values("포인트", ascending=False)
        rank_df = rank_df.reset_index(drop=True)
        rank_df.index = rank_df.index + 1 
        st.dataframe(rank_df, use_container_width=True)
        
        st.divider()
        
        # 4. 개인별 상세 분석
        st.subheader("🔍 개인별 상세 분석")
        
        player_list = rank_df['이름'].tolist()
        if player_list:
            selected_player = st.selectbox("선수를 선택하세요", player_list)
            
            if selected_player:
                p_stat = stats.get(selected_player)
                
                # (1) 기본 스탯
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🏅 랭킹 포인트", f"{p_stat['point']}점")
                c2.metric("총 경기수", f"{p_stat['경기']}전")
                win_rate_val = (p_stat['승'] / p_stat['경기'] * 100) if p_stat['경기'] > 0 else 0
                c3.metric("승률", f"{win_rate_val:.1f}%")
                c4.metric("종합 전적", f"{p_stat['승']}승 {p_stat['무']}무 {p_stat['패']}패")
                
                st.write("") 

                # (2) 최근 경기 기록
                st.markdown("##### 📜 최근 경기 기록 (Last 10 Matches)")
                
                mask = df['팀1'].apply(lambda x: selected_player in str(x)) | \
                       df['팀2'].apply(lambda x: selected_player in str(x))
                my_matches = df[mask].copy()
                recent_matches = my_matches.sort_values("날짜", ascending=False).head(10)

                # --- [핵심] 만능 승패 판독기 ---
                def check_match_result(row, me):
                    t1_str, t2_str = str(row['팀1']), str(row['팀2'])
                    win_str = str(row['승리팀'])
                    try: s1, s2 = int(row['점수1']), int(row['점수2'])
                    except: s1, s2 = 0, 0
                    
                    my_team_idx = 0
                    if me in t1_str: my_team_idx = 1
                    elif me in t2_str: my_team_idx = 2
                    
                    if my_team_idx == 0: return "error"

                    winner_idx = -1
                    # (A) 점수로 판별
                    if s1 != s2: winner_idx = 1 if s1 > s2 else 2
                    elif s1 == s2 and s1 > 0: winner_idx = 0
                    # (B) 텍스트로 판별
                    if winner_idx == -1:
                        if "무승부" in win_str: winner_idx = 0
                        elif t1_str in win_str: winner_idx = 1
                        elif t2_str in win_str: winner_idx = 2

                    if winner_idx == 0: return "draw"
                    if winner_idx == my_team_idx: return "win"
                    return "lose"
                # ------------------------------------
                
                if not recent_matches.empty:
                    display_history = []
                    for _, row in recent_matches.iterrows():
                        res = check_match_result(row, selected_player)
                        icon = "✅ 승" if res == "win" else "❌ 패" if res == "lose" else "🤝 무"
                        display_history.append({
                            "날짜": row['날짜'],
                            "결과": icon,
                            "매치업": f"{row['팀1']} vs {row['팀2']}",
                            "스코어": f"{row['점수1']} : {row['점수2']}"
                        })
                    st.dataframe(pd.DataFrame(display_history), hide_index=True, use_container_width=True)
                else:
                    st.info("경기 기록이 없습니다.")

                st.divider()

                # (3) 🧪 4대 천왕 분석
                st.markdown("##### 🧪 4대 천왕 분석 (파트너 & 천적)")
                
                teammate_stats = {} 
                opponent_stats = {} 
                
                for _, row in my_matches.iterrows():
                    res = check_match_result(row, selected_player)
                    if res == "error" or res == "draw": continue 

                    t1_list = str(row['팀1']).replace(',', ' ').split()
                    t2_list = str(row['팀2']).replace(',', ' ').split()
                    
                    my_team_list, opp_team_list = [], []
                    if selected_player in t1_list:
                        my_team_list, opp_team_list = t1_list, t2_list
                    elif selected_player in t2_list:
                        my_team_list, opp_team_list = t2_list, t1_list
                    
                    is_win = (res == "win")
                    
                    for m in my_team_list:
                        if m != selected_player:
                            if m not in teammate_stats: teammate_stats[m] = {'승':0, '경기':0}
                            teammate_stats[m]['경기'] += 1
                            if is_win: teammate_stats[m]['승'] += 1
                            
                    for m in opp_team_list:
                        if m != selected_player:
                            if m not in opponent_stats: opponent_stats[m] = {'승':0, '경기':0}
                            opponent_stats[m]['경기'] += 1
                            if is_win: opponent_stats[m]['승'] += 1

                def sort_stats(d):
                    lst = []
                    for k, v in d.items():
                        if v['경기'] > 0:
                            rate = (v['승'] / v['경기']) * 100
                            lst.append((k, rate, v['승'], v['경기']))
                    return sorted(lst, key=lambda x: (x[1], x[3]), reverse=True)
                
                sorted_team = sort_stats(teammate_stats)
                sorted_opp = sort_stats(opponent_stats)
                
                if sorted_team or sorted_opp:
                    col_best, col_worst = st.columns(2)
                    with col_best:
                        if sorted_team:
                            best = sorted_team[0]
                            st.success(f"💙 **환상의 짝꿍**: {best[0]}\n\n함께 승률 {best[1]:.1f}% ({best[3]}전 {best[2]}승)")
                        else: st.info("기록 없음")
                    with col_worst:
                        if sorted_opp:
                            prey = sorted_opp[0]
                            st.success(f"🍖 **맛있는 먹잇감**: {prey[0]}\n\n상대 승률 {prey[1]:.1f}% ({prey[3]}전 {prey[2]}승)")
                        else: st.info("기록 없음")

                    col_xman, col_nemesis = st.columns(2)
                    with col_xman:
                        if sorted_team:
                            xman = sorted_team[-1]
                            st.error(f"💔 **억제기 (X맨)**: {xman[0]}\n\n함께 승률 {xman[1]:.1f}% ({xman[3]}전 {xman[2]}승)")
                    with col_nemesis:
                        if sorted_opp:
                            nemesis = sorted_opp[-1]
                            st.error(f"👿 **천적 (담당일진)**: {nemesis[0]}\n\n상대 승률 {nemesis[1]:.1f}% ({nemesis[3]}전 {nemesis[2]}승)")
                else:
                    st.info("⚠️ 분석 데이터 부족")
        else:
            st.info("선수가 없습니다.")
    else:
        st.info("경기 기록이 없습니다.")



# [4] 경기 기록 관리
elif menu == "📝 경기 기록 관리":
    st.header("📝 경기 기록 관리 (구글 시트 연동됨)")
    df = load_data("경기기록", ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
    
    if df.empty:
        st.info("저장된 경기 기록이 없습니다.")
    else:
        df['날짜_short'] = df['날짜'].astype(str).apply(lambda x: x.split(' ')[0] if len(str(x)) > 5 else x)
        dates = sorted(df['날짜_short'].unique(), reverse=True)
        selected_date = st.selectbox("📅 날짜 선택", dates)
        filtered_df = df[df['날짜_short'] == selected_date].copy()
        
        if not filtered_df.empty:
            st.write(f"총 {len(filtered_df)}개의 경기가 있습니다.")
            filtered_df['삭제'] = False
            edited_df = st.data_editor(
                filtered_df[['삭제', '날짜', '팀1', '팀2', '점수1', '점수2', '승리팀', '경기ID']],
                column_config={
                    "삭제": st.column_config.CheckboxColumn("선택", help="삭제할 경기를 선택하세요"),
                    "경기ID": None
                },
                hide_index=True,
                width="stretch"
            )
            if st.button("🗑️ 선택한 경기 삭제"):
                to_delete = edited_df[edited_df['삭제']]['경기ID'].tolist()
                if to_delete:
                    with st.spinner("구글 시트에서 삭제 중..."):
                        delete_match_records(to_delete)
                    st.success(f"{len(to_delete)}건의 경기 기록이 삭제되었습니다. (포인트는 자동 재계산됩니다)")
                    st.rerun()
                else:
                    st.warning("삭제할 경기를 선택해주세요.")
        else:
            st.info("해당 날짜의 기록이 없습니다.")
