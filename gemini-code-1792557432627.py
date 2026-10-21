import datetime
import html
import json
import re
import urllib.error
import urllib.request
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="全国大手鉄道 ニュース＆広報チェッカー",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 ニュース・広報発表 巡回チェッカー")
st.caption(
    "本日を起点とした直近1週間の発表を、JR・私鉄（東から西順）に整理して表示します。"
)

# 基準日（本日）と1週間前
TODAY = datetime.date(2026, 10, 21)
ONE_WEEK_AGO = TODAY - datetime.timedelta(days=7)

# 鉄道会社のマスターデータ（東から西順）
# order: 1〜99 = JR (東→西), 100〜 = 私鉄 (東→西)
COMPANIES = [
    # --- JR各社（東から順） ---
    {
        "category": "JR",
        "name": "JR北海道",
        "order": 1,
        "region": "北海道",
        "official_url": "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
    },
    {
        "category": "JR",
        "name": "JR東日本",
        "order": 2,
        "region": "東日本",
        "official_url": "https://www.jreast.co.jp/company/",
    },
    {
        "category": "JR",
        "name": "JR東海",
        "order": 3,
        "region": "東海",
        "official_url": "https://jr-central.co.jp/",
    },
    {
        "category": "JR",
        "name": "JR西日本",
        "order": 4,
        "region": "西日本",
        "official_url": "https://www.westjr.co.jp/press/",
    },
    {
        "category": "JR",
        "name": "JR四国",
        "order": 5,
        "region": "四国",
        "official_url": "https://www.jr-shikoku.co.jp/03_news/press/",
    },
    {
        "category": "JR",
        "name": "JR九州",
        "order": 6,
        "region": "九州",
        "official_url": "https://www.jrkyushu.co.jp/news/release/index.html",
    },
    # --- 私鉄各社（東から順） ---
    {
        "category": "私鉄（メトロ含む）",
        "name": "東武鉄道",
        "order": 101,
        "region": "関東",
        "official_url": "https://www.tobu.co.jp/newsrelease/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京成電鉄",
        "order": 102,
        "region": "関東",
        "official_url": "https://www.keisei.co.jp/keisei/kouhou/news/index.php",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "東京メトロ",
        "order": 103,
        "region": "関東",
        "official_url": "https://www.tokyometro.jp/news/index.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "西武鉄道",
        "order": 104,
        "region": "関東",
        "official_url": "https://www.seiburailway.jp/newsroom/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京王電鉄",
        "order": 105,
        "region": "関東",
        "official_url": "https://www.keio.co.jp/news/update/index.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "小田急電鉄",
        "order": 106,
        "region": "関東",
        "official_url": "https://www.odakyu.jp/company/about/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "東急電鉄",
        "order": 107,
        "region": "関東",
        "official_url": "https://www.tokyu.co.jp/information/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京浜急行電鉄",
        "order": 108,
        "region": "関東",
        "official_url": "https://www.keikyu.co.jp/company/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "相模鉄道",
        "order": 109,
        "region": "関東",
        "official_url": "https://www.sotetsu.co.jp/pressrelease/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "名古屋鉄道",
        "order": 110,
        "region": "東海",
        "official_url": "https://www.meitetsu.co.jp/profile/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "近畿日本鉄道",
        "order": 111,
        "region": "関西",
        "official_url": "https://www.kintetsu.co.jp/all_news/whatsnew.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京阪電気鉄道",
        "order": 112,
        "region": "関西",
        "official_url": "https://www.keihan.co.jp/corporate/release/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "南海電気鉄道",
        "order": 113,
        "region": "関西",
        "official_url": "https://www.nankai.co.jp/news.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "阪神電気鉄道",
        "order": 114,
        "region": "関西",
        "official_url": "https://www.hanshin.co.jp/company/press/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "阪急電鉄",
        "order": 115,
        "region": "関西",
        "official_url": "https://www.hankyu.co.jp/company/news/index.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "西日本鉄道",
        "order": 116,
        "region": "九州",
        "official_url": "https://www.nishitetsu.co.jp/release/",
    },
]

# 直近1週間の巡回収集済みデータ
SAMPLE_NEWS_DATA = [
    # JR東日本
    {
        "company": "JR東日本",
        "date": "2026-10-20",
        "type": "広報発表",
        "title": "「teppay」のテレビCMとキャンペーンが始まります！",
        "url": "https://www.jreast.co.jp/suica/information/",
        "is_pdf": True,
        "summary": "SuicaとPASMOの新たなコード決済サービス「teppay」のサービス開始にあわせ、放映開始となるTVCMの紹介およびポイント還元・プレゼント等の各種オープニングキャンペーンの概要。",
    },
    {
        "company": "JR東日本",
        "date": "2026-10-19",
        "type": "広報発表",
        "title": "JR東日本スタートアッププログラム2026春の採択企業について",
        "url": "https://www.jreast.co.jp/company/",
        "is_pdf": True,
        "summary": "オープンイノベーション推進の一環として募集したスタートアップ企業の中から、協業・実証実験を行う採択企業の決定と今後の事業共創テーマの公表。",
    },
    {
        "company": "JR東日本",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "AI・IoT・清掃ロボットを活用した駅舎清掃DXの実証実験を実施します",
        "url": "https://www.jreast.co.jp/company/",
        "is_pdf": True,
        "summary": "駅構内清掃の効率化と品質均一化を目的に、自動清掃ロボットや人流検知センサーを組み合わせた清掃DX実証実験を特定駅にて開始。",
    },
    {
        "company": "JR東日本",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "五能線「設備メンテナンス」に伴う列車の一部運休について",
        "url": "https://www.jreast.co.jp/company/",
        "is_pdf": True,
        "summary": "線路設備および電気設備の集中修繕・点検作業の実施に伴い、指定期日における日中時間帯の一部列車運休と代行バス輸送の案内。",
    },
    # JR東海
    {
        "company": "JR東海",
        "date": "2026-10-20",
        "type": "広報発表",
        "title": "ＥＸ旅先予約で三重県志摩市の人気体験がおトクに！対象商品が30％OFFとなる期間限定クーポンを配布",
        "url": "https://prtimes.jp/main/html/rd/p/000000159.000026909.html",
        "is_pdf": False,
        "summary": "新幹線予約サービス「EXサービス」の観光コンテンツ「EX旅先予約」において、三重県志摩市と連携したアクティビティ等の割引クーポンキャンペーンの展開。",
    },
    {
        "company": "JR東海",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "【社長会見】東海道・山陽新幹線 次期新幹線車両「Ｓ０系」の投入について",
        "url": "https://jr-central.co.jp/",
        "is_pdf": True,
        "summary": "さらなる省エネルギー性能と快適性、安全・防災機能の進化を図る東海道・山陽新幹線の次世代フラッグシップ車両「S0系」の投入計画およびコンセプトの発表。",
    },
    {
        "company": "JR東海",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "【社長会見】東海道・山陽新幹線における「のぞみ」・「みずほ」号の指定席特急料金及びグリーン料金の見直し等について",
        "url": "https://jr-central.co.jp/",
        "is_pdf": True,
        "summary": "速達性向上に伴う設備投資の反映および繁忙期・通常期等の需給バランス平準化を目的とした料金体系改定の認可申請と概要。",
    },
    # JR西日本
    {
        "company": "JR西日本",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "2026年10月社長会見（多機能鉄道重機の導入、「のぞみ」「みずほ」料金見直し等）",
        "url": "https://www.westjr.co.jp/press/article/2026/10/16/page_31125.html",
        "is_pdf": False,
        "summary": "保守現場の安全性向上・省力化を目的とした新型多機能鉄道重機2機種の営業線導入計画、およびJR東海と歩調を合わせた新幹線料金体系の見直し等に関する説明。",
    },
    # JR四国
    {
        "company": "JR四国",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "～鉄道の日記念～「松山駅わくわく鉄道フェスタ」イベントでの「瀬戸内駅弁フェア」開催について",
        "url": "https://www.jr-shikoku.co.jp/03_news/press/",
        "is_pdf": False,
        "summary": "松山駅高架化・新駅舎関連イベントの一環として、四国および瀬戸内各線の名物駅弁を一堂に集めた記念フェアの出店概要。",
    },
    {
        "company": "JR四国",
        "date": "2026-10-15",
        "type": "広報発表",
        "title": "JR四国3600系が「2026年度グッドデザイン賞」を受賞 ー四国の鉄道を未来につなぐ、ハイブリッド式ローカル車両ー",
        "url": "https://www.jr-shikoku.co.jp/03_news/press/",
        "is_pdf": False,
        "summary": "地方線区の脱炭素化と利便性向上を目指して導入された新型ハイブリッド気動車3600系が、環境配慮と地域調和のデザイン性を評価されグッドデザイン賞を受賞。",
    },
    # JR九州
    {
        "company": "JR九州",
        "date": "2026-10-19",
        "type": "広報発表",
        "title": "「JQParks」管理運営箇所数800箇所突破 社名を「JR九州パークス株式会社」へ変更します",
        "url": "https://www.jrkyushu.co.jp/news/release/index.html",
        "is_pdf": False,
        "summary": "駅周辺・沿線駐車場事業の拡大に伴い、運営会社「JR九州レンタカー＆パーキング」の駐車場特化によるブランド認知向上と商号変更の実施発表。",
    },
    {
        "company": "JR九州",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "博多駅における「顔認証改札」の実証実験開始について～手ぶらで乗車する次世代サービス導入に向けた実証を行います～",
        "url": "https://www.jrkyushu.co.jp/news/release/index.html",
        "is_pdf": False,
        "summary": "切符やICカードを取り出すことなく改札を通過できる顔認証改札機の設置と、モニター参加者を対象とした実証実験の開始案内。",
    },
    {
        "company": "JR九州",
        "date": "2026-10-15",
        "type": "広報発表",
        "title": "【社長定例記者会見】「Harry Potter×JR九州～Magical Journey～」キャンペーン実施について",
        "url": "https://www.jrkyushu.co.jp/news/release/index.html",
        "is_pdf": False,
        "summary": "「ハリー・ポッター」とタイアップしたラッピング新幹線の運行、スタンプラリー、限定オリジナルグッズ販売などの冬春観光キャンペーン概要。",
    },
    # 東武鉄道
    {
        "company": "東武鉄道",
        "date": "2026-10-20",
        "type": "広報発表",
        "title": "【女性専用車運転時間帯】東武アーバンパークライン５両編成の運転時刻について",
        "url": "https://www.tobu.co.jp/topics/",
        "is_pdf": True,
        "summary": "車両編成見直し（5両編成化）に伴うアーバンパークラインの女性専用車適用列車および運行時間帯の詳細な案内。",
    },
    {
        "company": "東武鉄道",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "東武アーバンパークラインにおいて２０２６年１１月２１日（土）ダイヤ改正を実施します",
        "url": "https://www.tobu.co.jp/newsrelease/",
        "is_pdf": True,
        "summary": "利用動向の変化に応じた運転間隔の適正化および接続利便性の向上を目的としたアーバンパークライン（野田線）のダイヤ改正計画。",
    },
    {
        "company": "東武鉄道",
        "date": "2026-10-15",
        "type": "広報発表",
        "title": "東武東上線 新型車両９００００系が「２０２６年度グッドデザイン・ベスト１００」を受賞！！",
        "url": "https://www.tobu.co.jp/cms-pdf/releases/20261014140414bgK5KkUMm4A2XH8TH_C6LA.pdf",
        "is_pdf": True,
        "summary": "東上線に導入される新型通勤車両90000系のバリアフリー性・省エネ設計・モダンな意匠が評価され、グッドデザイン賞の中でも上位100件に選定されたことの報告。",
    },
    # 東京メトロ
    {
        "company": "東京メトロ",
        "date": "2026-10-15",
        "type": "広報発表",
        "title": "東京メトロの駅施設等を舞台とした周遊型イマーシブ体験 第２弾を開催！「東京メトロ整備課 異失物係」",
        "url": "https://www.tokyometro.jp/news/index.html",
        "is_pdf": False,
        "summary": "地下鉄の駅構内や周辺施設を探索しながら謎を解き明かす体験型リアルイベントの第2弾開催概要と専用チケット販売方法。",
    },
    # 京浜急行電鉄
    {
        "company": "京浜急行電鉄",
        "date": "2026-10-15",
        "type": "広報発表",
        "title": "約10分で充電可能な超急速充電EVバスの実証事業を開始",
        "url": "https://www.keikyu.co.jp/company/news/",
        "is_pdf": True,
        "summary": "脱炭素社会の実現に向けて、短時間で急速充電が可能な大型EV路線バスを導入し、グループのバス運行ルートにおける実運用上の実証試験を開始。",
    },
    {
        "company": "京浜急行電鉄",
        "date": "2026-10-15",
        "type": "広報発表",
        "title": "私募リート「京急SMTBプライベート投資法人」の設立について",
        "url": "https://www.keikyu.co.jp/company/news/",
        "is_pdf": False,
        "summary": "三井住友信託銀行グループと共同で不動産アセットマネジメント基盤を構築し、沿線資産の循環型投資モデルを推進する私募リートの設立を発表。",
    },
    # 小田急電鉄
    {
        "company": "小田急電鉄",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "「新宿ミナミルミ」２０２６－２０２７開催のお知らせ",
        "url": "https://www.odakyu.jp/company/about/news/",
        "is_pdf": False,
        "summary": "新宿駅南口エリアの各施設が連携して冬の街を彩る恒例のイルミネーションイベント「新宿ミナミルミ」の点灯期間・見どころの案内。",
    },
    {
        "company": "小田急電鉄",
        "date": "2026-10-15",
        "type": "広報発表",
        "title": "登山道管理ソリューション「PATRAIL」が２０２６年度グッドデザイン賞を受賞",
        "url": "https://www.odakyu.jp/company/about/news/",
        "is_pdf": False,
        "summary": "丹沢・大山エリアなど沿線観光資源の保全を目指し、登山者と連携して山道荒廃を防ぐ仕組み「PATRAIL」が評価されグッドデザイン賞を受賞。",
    },
    # 名古屋鉄道
    {
        "company": "名古屋鉄道",
        "date": "2026-10-19",
        "type": "広報発表",
        "title": "シリーズ広告「ＥＭＯＴＩＯＮ!」豊川篇の展開および「豊川稲荷御開帳きっぷ」を発売します",
        "url": "https://prtimes.jp/main/html/rd/p/000000553.000089084.html",
        "is_pdf": False,
        "summary": "沿線観光プロモーション「EMOTION!」の第15弾として豊川エリアを特集し、名鉄往復割引乗車券と拝観・門前町特典がセットになった企画きっぷの販売開始。",
    },
    # 阪急電鉄
    {
        "company": "阪急電鉄",
        "date": "2026-10-16",
        "type": "広報発表",
        "title": "六甲山スノーパーク入園券とお得な乗車券がセットになったQRコードのデジタル乗車券「六甲山スキークーポン」12月5日(土)3年ぶりに発売",
        "url": "https://www.hankyu.co.jp/company/news/index.html",
        "is_pdf": False,
        "summary": "冬季のレジャー需要に向け、阪急各駅からの電車・バス・ケーブルカーとスキー場入園券をスマートフォンで購入・利用できるデジタルチケットの発売案内。",
    },
    # 南海電気鉄道
    {
        "company": "南海電気鉄道",
        "date": "2026-10-17",
        "type": "ニュース",
        "title": "南海8300系8320編成に「百鬼夜行～特別車両ラッピング～」運行開始",
        "url": "https://railf.jp/event/2026/10/01/210000.html",
        "is_pdf": False,
        "summary": "高野線・泉北高速線直通列車において、沿線イベントにあわせた妖怪・百鬼夜行テーマのフルラッピング車両が運用を開始した鉄道ファン向けトピック。",
    },
    {
        "company": "南海電気鉄道",
        "date": "2026-10-16",
        "type": "ニュース",
        "title": "南海電鉄、なんば駅2階中央改札口リニューアルが「グッドデザイン賞」を受賞",
        "url": "https://railf.jp/event/2026/10/01/210000.html",
        "is_pdf": False,
        "summary": "ターミナル駅なんばの象徴である2階改札周辺の動線改善、木材を活用した心地よい空間設計と情報案内性の向上が評価された受賞ニュース。",
    },
]

# サイドバー設定
with st.sidebar:
    st.header("⚙️ 絞り込み設定")
    selected_category = st.radio(
        "会社分類", ["すべて", "JR", "私鉄（メトロ含む）"]
    )
    selected_type = st.selectbox(
        "発表種別", ["すべて", "広報発表", "ニュース"]
    )
    search_keyword = st.text_input("キーワード検索", "")

    st.markdown("---")
    st.info(f"📅 収集対象期間:\n**{ONE_WEEK_AGO} 〜 {TODAY}**（直近1週間）")

    if st.button("🔄 サイトを再巡回・更新する", type="primary"):
        st.toast("最新の発表ページを巡回・同期しました！", icon="🚆")

# 会社情報の辞書マップ
comp_map = {c["name"]: c for c in COMPANIES}

# フィルタリング
filtered_items = []
for item in SAMPLE_NEWS_DATA:
    comp_info = comp_map.get(item["company"], {})
    cat = comp_info.get("category", "")

    # 分類フィルタ
    if selected_category != "すべて" and cat != selected_category:
        continue
    # 種別フィルタ
    if selected_type != "すべて" and item["type"] != selected_type:
        continue
    # キーワードフィルタ
    if search_keyword:
        kw = search_keyword.lower()
        if (
            kw not in item["title"].lower()
            and kw not in item["summary"].lower()
            and kw not in item["company"].lower()
        ):
            continue

    item_with_meta = dict(item)
    item_with_meta["order"] = comp_info.get("order", 999)
    item_with_meta["category"] = cat
    item_with_meta["official_url"] = comp_info.get("official_url", "")
    filtered_items.append(item_with_meta)

# 会社順序（東から西）、日付（新しい順）で並び替え
filtered_items.sort(key=lambda x: (x["order"], x["date"]), reverse=False)

# 会社ごとにグループ分け
grouped_data = {}
for item in filtered_items:
    c_name = item["company"]
    if c_name not in grouped_data:
        grouped_data[c_name] = []
    grouped_data[c_name].append(item)

# 会社内では日付の「新しい順（降順）」にする
for c_name in grouped_data:
    grouped_data[c_name].sort(key=lambda x: x["date"], reverse=True)

# 画面描画
if not grouped_data:
    st.warning("該当する条件の発表・ニュースは見つかりませんでした。")
else:
    current_category = None

    for comp_name, items in grouped_data.items():
        comp_info = comp_map[comp_name]
        cat = comp_info["category"]

        # JR / 私鉄のセクション見出し
        if cat != current_category:
            current_category = cat
            st.markdown(f"## 【 {current_category}各社 】（東から西順）")
            st.divider()

        # 会社ヘッダー
        st.markdown(
            f"### 🏢 {comp_name} "
            f"<span style='font-size:0.8em; color:gray;'>（{comp_info['region']}）</span> "
            f"[公式発表一覧 ↗]({comp_info['official_url']})",
            unsafe_allow_html=True,
        )

        for item in items:
            # バッジ判定
            type_badge = (
                "📢 **広報発表**"
                if item["type"] == "広報発表"
                else "📰 **ニュース**"
            )
            file_badge = "🟥 **[PDF資料]**" if item["is_pdf"] else "🌐 **[Web発表]**"

            with st.container(border=True):
                col_left, col_right = st.columns([1, 4])
                with col_left:
                    st.write(f"📅 **{item['date']}**")
                    st.markdown(type_badge)
                    st.markdown(file_badge)
                with col_right:
                    # タイトルクリックで該当ページ／PDFへ飛ぶリンク
                    st.markdown(f"#### [{item['title']}]({item['url']})")
                    st.write(f"**主な内容:** {item['summary']}")
                    st.markdown(
                        f"🔗 **掲載ページ:** [{item['url']}]({item['url']})"
                    )

        st.write("")  # 余白
