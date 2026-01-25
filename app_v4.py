import streamlit as st
import random
import pandas as pd
import os
import math
import matplotlib.pyplot as plt
from datetime import datetime

# --- 설정 및 한글 폰트 ---
st.set_page_config(page_title="행님표 테니스 ERP V4.0 (Point)", page_icon="🎾", layout="wide")

# [폰트 설정]
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# --- 파일 경로 ---
MATCH_FILE = 'match_history.csv'
MEMBER_FILE = 'members.csv'

# --- 데이터 관리 함수 ---
def load_data(file, columns):
    if not os.path.exists(file):
        return pd.DataFrame(columns=columns)
    return pd.read_csv(file)

def save_data(df, file):
    df.to_csv(file, index=False)

def add_match_record(t1, t2, s1, s2):
    df = load_data(MATCH_FILE, ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
    winner = t1 if s1 > s2 else (t2 if s2 > s1 else "무승부")
    match_id = datetime.now().strftime("%Y%m%d%H%M%S")
    new_data = {
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "경기ID": match_id,
        "팀1": t1, "팀2": t2, "점수1": s1, "점수2": s2, "승리팀": winner
    }
    new_df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
    save_data(new_df, MATCH_FILE)
    return new_df

def delete_match_records(match_ids):
    df = load_data(MATCH_FILE, ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
    if df.empty: return
    df['경기ID'] = df['경기ID'].astype(str)
    new_df = df[~df['경기ID'].isin([str(x) for x in match_ids])]
    save_data(new_df, MATCH_FILE)

# --- [핵심] Elo 포인트 계산 로직 ---
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
    df = df.sort_values("날짜")

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

        except Exception as e:
            continue
    return stats

# --- AI 팀 밸런싱 ---
def balance_teams_by_point(players, stats):
    sorted_p = sorted(players, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
    team_a, team_b = [], []
    for i, p in enumerate(sorted_p):
        if i % 4 in [0, 3]: team_a.append(p)
        else: team_b.append(p)
    return team_a, team_b

# --- 스케줄러 ---
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

# --- 토너먼트 시각화 ---
def draw_bracket_plot(teams_4):
    winners = st.session_state.get('tourney_winners', {})
    semi_1_t1, semi_1_t2 = teams_4[0], teams_4[1]
    semi_2_t1, semi_2_t2 = teams_4[2], teams_4[3]
    final_1 = winners.get('semi_1', '???')
    final_2 = winners.get('semi_2', '???')
    champion = winners.get('final', '최종 우승') 

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis('off')
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
st.title("🎾 행님표 ERP V4.0 [Elo 포인트 랭킹]")
st.caption("고수를 잡으면 점수 대박! 양민 학살은 점수 찔끔! 공정한 실력 시스템")

menu = st.sidebar.radio("메뉴", ["👥 회원 관리", "🏟️ 경기 운영", "📊 Elo 랭킹 & 분석", "📝 경기 기록 관리"])

# [1] 회원 관리
if menu == "👥 회원 관리":
    st.header("회원 명부")
    col1, col2 = st.columns([2, 1])
    member_df = load_data(MEMBER_FILE, ["이름", "가입일", "메모"])
    with col1: st.dataframe(member_df, width="stretch", hide_index=True)
    with col2:
        with st.form("add"):
            name = st.text_input("이름")
            memo = st.text_input("메모")
            if st.form_submit_button("등록"):
                if name and name not in member_df["이름"].values:
                    new = pd.DataFrame([{"이름": name, "가입일": datetime.now().strftime("%Y-%m-%d"), "메모": memo}])
                    save_data(pd.concat([member_df, new], ignore_index=True), MEMBER_FILE)
                    st.rerun()

# [2] 경기 운영
elif menu == "🏟️ 경기 운영":
    st.header("매치 메이킹 시스템")
    mode_tab1, mode_tab2, mode_tab3, mode_tab4 = st.tabs(["🔄 일반 매칭", "🏆 토너먼트", "⚔️ 팀 대항전", "🔢 KDK (개인전)"])
    member_df = load_data(MEMBER_FILE, ["이름"])
    
    # 2.1 일반 매칭
    with mode_tab1:
        if not member_df.empty:
            # [수정] default=... 부분 제거하여 처음에 아무도 선택되지 않게 함
            attendees = st.multiselect("출석 체크", member_df["이름"].tolist(), key="league_att")
            c1, c2 = st.columns(2)
            with c1: target_games = st.slider("인당 게임 수", 1, 6, 3)
            with c2: match_mode = st.radio("방식", ["🎲 랜덤 복식", "⚖️ 황금 밸런스(Elo)"], horizontal=True, key="league_mode")
            if st.button("🚀 리그 대진표 생성", type="primary"):
                hist = load_data(MATCH_FILE, ["승리팀", "팀1", "팀2"])
                stats = get_player_stats_and_elo(hist, member_df["이름"].tolist())
                st.session_state.schedule = generate_league_schedule(attendees, target_games, match_mode, stats)
                st.session_state.is_generated = True
            if 'is_generated' in st.session_state and st.session_state.is_generated:
                st.divider()
                for round_data in st.session_state.schedule:
                    r_num = round_data['round_num']
                    st.markdown(f"**Round {r_num}**")
                    for idx, match in enumerate(round_data['matches']):
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([2,1,1])
                            c1.caption(f"{match['t1']} vs {match['t2']}")
                            s1 = c2.number_input("점1", key=f"r{r_num}m{idx}s1", min_value=0, max_value=7)
                            s2 = c3.number_input("점2", key=f"r{r_num}m{idx}s2", min_value=0, max_value=7)
                            if st.button("기록", key=f"btn_r{r_num}m{idx}"):
                                add_match_record(match['t1'], match['t2'], s1, s2)
                                st.toast("저장 및 포인트 갱신 완료!")

    # 2.2 토너먼트
    with mode_tab2:
        st.info("💡 4~8팀. 부전승 자동 처리.")
        t_attendees = st.multiselect("참가 선수", member_df["이름"].tolist(), key="tourney_att")
        c1, c2 = st.columns(2)
        with c1: team_cnt = st.selectbox("팀 수", [4, 5, 6, 7, 8])
        with c2: team_method = st.selectbox("방식", ["⚖️ 황금 밸런스(Elo)", "🎲 랜덤", "👆 수동"])
        
        manual_teams = []
        if team_method == "👆 수동":
            cols = st.columns(2)
            for i in range(team_cnt):
                with cols[i%2]:
                    p1 = st.selectbox(f"T{i+1}-1", t_attendees, key=f"man_t{i}_1")
                    p2 = st.selectbox(f"T{i+1}-2", t_attendees, key=f"man_t{i}_2")
                    manual_teams.append(f"{p1}, {p2}")
        if st.button("🏟️ 대회 시작", key="start_tourney"):
            final_teams = []
            if team_method == "🎲 랜덤":
                random.shuffle(t_attendees)
                final_teams = [f"{t_attendees[i*2]}, {t_attendees[i*2+1]}" for i in range(team_cnt)]
            elif team_method == "⚖️ 황금 밸런스(Elo)":
                hist = load_data(MATCH_FILE, ["승리팀", "팀1", "팀2"])
                stats = get_player_stats_and_elo(hist, member_df["이름"].tolist())
                sorted_p = sorted(t_attendees, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
                final_teams = [f"{sorted_p[i]}, {sorted_p[len(sorted_p)-1-i]}" for i in range(team_cnt)]
            elif team_method == "👆 수동":
                final_teams = manual_teams
            st.session_state.tourney_teams = final_teams
            st.session_state.tourney_winners = {}
            st.session_state.tourney_active = True
            st.session_state.tourney_step = "PRE" if team_cnt > 4 else "SF"
            st.session_state.matches_needed = team_cnt - 4
            st.rerun()
            
        if st.session_state.get('tourney_active'):
            teams = st.session_state.tourney_teams
            winners = st.session_state.get('tourney_winners', {})
            step = st.session_state.get('tourney_step', 'SF')
            st.divider()
            if step == "PRE":
                n_matches = st.session_state.matches_needed
                st.subheader("🔥 예선전")
                cols = st.columns(4)
                all_done = True
                for i in range(n_matches):
                    t1, t2 = teams[i*2], teams[i*2+1]
                    key = f"PRE_{i}"
                    with cols[i]:
                        st.caption(f"{t1} vs {t2}")
                        if key not in winners:
                            all_done = False
                            s1 = st.number_input("점1", key=f"pre_s1_{i}", max_value=7)
                            s2 = st.number_input("점2", key=f"pre_s2_{i}", max_value=7)
                            if st.button("입력", key=f"pre_btn_{i}"):
                                winners[key] = t1 if s1 > s2 else t2
                                add_match_record(t1, t2, s1, s2)
                                st.rerun()
                        else: st.success(f"승: {winners[key]}")
                if all_done:
                    if st.button("🚀 4강 대진표 생성"):
                        st.session_state.sf_teams = list(winners.values()) + teams[n_matches*2:]
                        st.session_state.tourney_step = "SF"; st.rerun()
            elif step == "SF":
                sf_teams = st.session_state.get('sf_teams', teams)
                st.pyplot(draw_bracket_plot(sf_teams))
                c1, c2 = st.columns(2)
                for i, loc in enumerate(['semi_1', 'semi_2']):
                    with [c1, c2][i]:
                        t1, t2 = sf_teams[i*2], sf_teams[i*2+1]
                        st.write(f"4강 {i+1}: {t1} vs {t2}")
                        if loc not in winners:
                            s1 = st.number_input("점1", key=f"sf_s1_{i}", max_value=7)
                            s2 = st.number_input("점2", key=f"sf_s2_{i}", max_value=7)
                            if st.button("입력", key=f"sf_btn_{i}"):
                                winners[loc] = t1 if s1 > s2 else t2
                                add_match_record(t1, t2, s1, s2)
                                st.rerun()
                if 'semi_1' in winners and 'semi_2' in winners:
                    st.divider()
                    st.markdown(f"### 결승: {winners['semi_1']} vs {winners['semi_2']}")
                    if 'final' not in winners:
                        s1 = st.number_input("점1", key="fin_s1", max_value=7)
                        s2 = st.number_input("점2", key="fin_s2", max_value=7)
                        if st.button("우승 확정", key="fin_btn"):
                            winners['final'] = winners['semi_1'] if s1 > s2 else winners['semi_2']
                            add_match_record(winners['semi_1'], winners['semi_2'], s1, s2)
                            st.balloons(); st.rerun()

    # 2.3 팀 대항전
    with mode_tab3:
        st.info("⚔️ A팀 vs B팀 끝장 승부")
        att_battle = st.multiselect("참석자", member_df["이름"].tolist(), key="battle_att")
        
        c1, c2 = st.columns(2)
        with c1: battle_mode = st.radio("팀 구성 방식", ["⚖️ 황금 밸런스(Elo)", "👆 수동(지명)"], key="bt_mode")
        with c2: game_count = st.slider("총 경기 수(판)", 3, 9, 5, step=2)

        manual_A, manual_B = [], []
        if battle_mode == "👆 수동(지명)":
            st.markdown("##### 팀원 구성")
            mc1, mc2 = st.columns(2)
            with mc1: manual_A = st.multiselect("🔵 A팀 선수", att_battle, key="mA")
            with mc2: manual_B = st.multiselect("🔴 B팀 선수", [x for x in att_battle if x not in manual_A], key="mB")

        if st.button("⚖️ 팀 나누기 & 시작"):
             valid = True
             if battle_mode == "⚖️ 황금 밸런스(Elo)":
                 hist = load_data(MATCH_FILE, ["승리팀", "팀1", "팀2"])
                 stats = get_player_stats_and_elo(hist, member_df["이름"].tolist())
                 ta, tb = balance_teams_by_point(att_battle, stats)
             else:
                 if not manual_A or not manual_B:
                     st.error("팀원을 모두 선택해주세요.")
                     valid = False
                 ta, tb = manual_A, manual_B
             
             if valid:
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
             score_a = sum(1 for m in matches if m.get('winner') == 'A')
             score_b = sum(1 for m in matches if m.get('winner') == 'B')
             st.markdown(f"### 🔵 A팀 {score_a} : {score_b} B팀 🔴")
             with st.expander("팀 명단 확인"):
                 st.write(f"**A팀:** {', '.join(ta)}")
                 st.write(f"**B팀:** {', '.join(tb)}")

             for i, m in enumerate(matches):
                 with st.expander(f"제 {i+1}경기 ({'완료' if m['done'] else '진행중'})", expanded=not m['done']):
                     if not m['done']:
                         c1, c2, c3 = st.columns([2, 0.5, 2])
                         curr_a = m['t1'].split(', ')
                         new_a1 = c1.selectbox(f"A1-{i}", ta, index=ta.index(curr_a[0]) if curr_a[0] in ta else 0)
                         new_a2 = c1.selectbox(f"A2-{i}", ta, index=ta.index(curr_a[1]) if curr_a[1] in ta else 0)
                         curr_b = m['t2'].split(', ')
                         new_b1 = c3.selectbox(f"B1-{i}", tb, index=tb.index(curr_b[0]) if curr_b[0] in tb else 0)
                         new_b2 = c3.selectbox(f"B2-{i}", tb, index=tb.index(curr_b[1]) if curr_b[1] in tb else 0)
                         s1, s2 = st.columns(2)
                         sc1 = s1.number_input("A점수", key=f"ba_s1_{i}", max_value=7)
                         sc2 = s2.number_input("B점수", key=f"ba_s2_{i}", max_value=7)
                         if st.button("결과 저장", key=f"ba_btn_{i}"):
                             m['t1'], m['t2'] = f"{new_a1}, {new_a2}", f"{new_b1}, {new_b2}"
                             m['winner'] = 'A' if sc1 > sc2 else 'B'
                             m['done'] = True
                             add_match_record(m['t1'], m['t2'], sc1, sc2)
                             st.rerun()
                     else: st.info(f"{m['winner']}팀 승리!")

    # 2.4 KDK
    with mode_tab4:
        st.info("🔢 파트너를 바꿔가며 진행하는 개인전")
        kdk_att = st.multiselect("참가자", member_df["이름"].tolist(), key="kdk_att")
        kdk_rounds = st.slider("진행할 총 라운드 수", 1, 6, 4, key="kdk_rds")

        if st.button("🎲 대진표 생성"):
             if len(kdk_att) < 4:
                 st.error("최소 4명 이상이어야 합니다.")
             else:
                 st.session_state.kdk_schedule = generate_kdk_schedule(kdk_att, kdk_rounds)
                 st.session_state.kdk_scores = {}
                 st.session_state.kdk_active = True
                 st.rerun()
        
        if st.session_state.get('kdk_active'):
            schedule = st.session_state.kdk_schedule
            scores = st.session_state.get('kdk_scores', {})
            rank_data = {p: {"승": 0, "패": 0, "득실": 0, "경기수":0} for p in kdk_att}
            for r in schedule:
                for idx, m in enumerate(r['matches']):
                    key = f"kdk_r{r['round']}_m{idx}"
                    if key in scores and scores[key]['done']:
                        s = scores[key]
                        diff = s['s1'] - s['s2']
                        t1, t2 = [x.strip() for x in m['t1'].split(',')], [x.strip() for x in m['t2'].split(',')]
                        for p in t1:
                            rank_data[p]['경기수'] += 1; rank_data[p]['득실'] += diff
                            if s['s1'] > s['s2']: rank_data[p]['승'] += 1
                            else: rank_data[p]['패'] += 1
                        for p in t2:
                            rank_data[p]['경기수'] += 1; rank_data[p]['득실'] -= diff
                            if s['s2'] > s['s1']: rank_data[p]['승'] += 1
                            else: rank_data[p]['패'] += 1
            
            rank_list = []
            for p, d in rank_data.items():
                win_rate = (d['승']/d['경기수']*100) if d['경기수'] > 0 else 0.0
                rank_list.append({"이름": p, "승": d['승'], "패": d['패'], "득실": d['득실'], "승률": f"{win_rate:.1f}%"})
            st.markdown("### 👑 실시간 KDK 랭킹")
            kdk_df = pd.DataFrame(rank_list).sort_values(["승", "득실"], ascending=False)
            kdk_df.reset_index(drop=True, inplace=True)
            kdk_df.index = kdk_df.index + 1
            kdk_df.reset_index(inplace=True)
            kdk_df.rename(columns={'index': '순위'}, inplace=True)
            st.dataframe(kdk_df, width="stretch")

            for r in schedule:
                with st.expander(f"Round {r['round']}", expanded=True):
                    cols = st.columns(len(r['matches']))
                    for idx, m in enumerate(r['matches']):
                        key = f"kdk_r{r['round']}_m{idx}"
                        if key not in scores:
                            with cols[idx]:
                                st.caption(f"{m['t1']} vs {m['t2']}")
                                c1, c2 = st.columns(2)
                                s1 = c1.number_input("점1", key=f"k_s1_{key}", max_value=7)
                                s2 = c2.number_input("점2", key=f"k_s2_{key}", max_value=7)
                                if st.button("입력", key=f"k_btn_{key}"):
                                    st.session_state.kdk_scores[key] = {'s1': s1, 's2': s2, 'done': True}
                                    add_match_record(m['t1'], m['t2'], s1, s2)
                                    st.rerun()

# [3] Elo 랭킹 & 분석
elif menu == "📊 Elo 랭킹 & 분석":
    st.header("🏆 Elo 포인트 랭킹")
    st.info("기본 1000점 시작. 승리시 점수 획득, 패배시 차감. (상대 실력에 따라 가중치 적용)")
    
    member_df = load_data(MEMBER_FILE, ["이름"])
    df = load_data(MATCH_FILE, ["날짜", "승리팀", "팀1", "팀2"])
    
    if df.empty:
        st.info("데이터가 없습니다.")
    else:
        member_list = member_df["이름"].tolist()
        stats = get_player_stats_and_elo(df, member_list)
        
        rank_data = []
        for p, d in stats.items():
            if d['경기'] > 0:
                win_rate = (d['승'] / d['경기'] * 100)
                rank_data.append({
                    "이름": p, 
                    "포인트": d['point'],
                    "승률": f"{win_rate:.1f}%",
                    "승": d['승'], "패": d['패'], "경기": d['경기']
                })
        
        rank_df = pd.DataFrame(rank_data).sort_values("포인트", ascending=False)
        rank_df.reset_index(drop=True, inplace=True)
        rank_df.index = rank_df.index + 1
        rank_df.reset_index(inplace=True)
        rank_df.rename(columns={'index': '순위'}, inplace=True)
        
        st.dataframe(
            rank_df, 
            width="stretch", 
            hide_index=True,
            column_config={
                "순위": st.column_config.NumberColumn("순위", width="small"),
                "이름": st.column_config.TextColumn("이름", width="medium"),
                "포인트": st.column_config.ProgressColumn("포인트 (Elo)", min_value=800, max_value=1200, format="%d pts"),
                "승률": st.column_config.TextColumn("승률", width="small"),
                "승": st.column_config.NumberColumn("승", width="small"),
                "패": st.column_config.NumberColumn("패", width="small"),
                "경기": st.column_config.NumberColumn("전", width="small")
            }
        )
        
        st.divider()

        st.subheader("🔍 선수별 심층 분석")
        target = st.selectbox("분석할 회원을 선택하세요:", [p['이름'] for p in rank_data])
        
        if target:
            my_matches = df[df['팀1'].str.contains(target) | df['팀2'].str.contains(target)]
            st.caption(f"* {target}님의 총 경기 수: {len(my_matches)}게임 기반 분석")
            partner_stats, enemy_stats = {}, {}

            for _, row in my_matches.iterrows():
                t1 = [x.strip() for x in row['팀1'].split(',')]
                t2 = [x.strip() for x in row['팀2'].split(',')]
                my_team = t1 if target in t1 else t2
                op_team = t2 if target in t1 else t1
                win = (row['승리팀'] != "무승부") and (target in row['승리팀'])

                for p in my_team:
                    if p != target:
                        if p not in partner_stats: partner_stats[p] = [0, 0]
                        partner_stats[p][1] += 1
                        if win: partner_stats[p][0] += 1
                for e in op_team:
                    if e not in enemy_stats: enemy_stats[e] = [0, 0]
                    enemy_stats[e][1] += 1
                    if win: enemy_stats[e][0] += 1

            def get_stat(stats, mode='best'):
                valid = {k:v for k,v in stats.items() if v[1]>=1}
                if not valid: return "-", 0.0
                rates = {k:v[0]/v[1]*100 for k,v in valid.items()}
                if mode == 'best': key = max(rates, key=rates.get)
                else: key = min(rates, key=rates.get)
                return key, rates[key]

            best_p, best_r = get_stat(partner_stats, 'best')
            worst_p, worst_r = get_stat(partner_stats, 'worst')
            easy_e, easy_r = get_stat(enemy_stats, 'best')
            hard_e, hard_r = get_stat(enemy_stats, 'worst')

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💙 환상의 짝꿍", best_p, f"{best_r:.1f}%")
            c2.metric("💔 억제기 (X맨)", worst_p, f"{worst_r:.1f}%", delta_color="inverse")
            c3.metric("🍖 맛있는 먹잇감", easy_e, f"{easy_r:.1f}%")
            c4.metric("👿 천적 (담당일진)", hard_e, f"{hard_r:.1f}%", delta_color="inverse")

# [4] 경기 기록 관리
elif menu == "📝 경기 기록 관리":
    st.header("📝 경기 기록 관리")
    df = load_data(MATCH_FILE, ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
    
    if df.empty:
        st.info("저장된 경기 기록이 없습니다.")
    else:
        df['날짜_short'] = df['날짜'].apply(lambda x: x.split(' ')[0])
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
                    delete_match_records(to_delete)
                    st.success(f"{len(to_delete)}건의 경기 기록이 삭제되었습니다. (포인트는 자동 재계산됩니다)")
                    st.rerun()
                else:
                    st.warning("삭제할 경기를 선택해주세요.")
        else:
            st.info("해당 날짜의 기록이 없습니다.")
