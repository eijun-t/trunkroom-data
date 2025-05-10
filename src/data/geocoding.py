import os
import sys

# プロジェクトのルートパスを動的に計算
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, root_path)

import streamlit as st
from src.auth.auth import login, signup, get_supabase_client
from geopy.geocoders import Nominatim

# Google Maps APIキーを環境変数から取得
from dotenv import load_dotenv
load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

def get_nearby_facilities(lat, lng, limit=15):
    """指定した緯度経度に近い施設を取得する"""
    supabase = get_supabase_client()
    try:
        # 距離計算はPostgreSQLの地理関数を使用
        query = supabase.rpc(
            'find_nearest_facilities',
            {
                'target_lat': lat,
                'target_lng': lng,
                'max_results': limit
            }
        ).execute()
        
        return query.data
    except Exception as e:
        st.error(f"施設情報の取得中にエラーが発生しました: {str(e)}")
        return []

def display_facilities(facilities):
    """施設のリストを表示する"""
    if not facilities:
        st.info("近くの施設が見つかりませんでした。")
        return
        
    st.subheader(f"近くの施設 ({len(facilities)}件)")
    
    for facility in facilities:
        with st.expander(f"{facility['name']}"):
            cols = st.columns([2, 1])
            with cols[0]:
                st.write(f"**住所**: {facility['address']}")
                if facility.get('min_price'):
                    st.write(f"**最低料金**: {facility['min_price']:,}円～")
                if facility.get('min_size'):
                    st.write(f"**最小サイズ**: {facility['min_size']}㎡～")

                # アメニティ情報
                amenities = []
                if facility.get('has_elevator'):
                    amenities.append("エレベーター有")
                if facility.get('has_security'):
                    amenities.append("セキュリティ有")
                if facility.get('has_airconditioner'):
                    amenities.append("空調有")
                if amenities:
                    st.write("**設備**: " + ", ".join(amenities))
                    
            with cols[1]:
                # 施設への詳細リンク
                st.write("**詳細情報**")
                st.link_button("物件を見る", f"/facility/{facility['id']}")

def create_google_map_html(center_lat, center_lng, markers=None, zoom=14, height=500):
    """GoogleマップのHTML要素を生成"""
    if markers is None:
        markers = []
        
    # Google Maps JavaScript APIを使用してHTMLを生成
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Google Maps</title>
        <style>
            #map {{
                height: {height}px;
                width: 100%;
            }}
            html, body {{
                height: 100%;
                margin: 0;
                padding: 0;
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            function initMap() {{
                const map = new google.maps.Map(document.getElementById("map"), {{
                    center: {{ lat: {center_lat}, lng: {center_lng} }},
                    zoom: {zoom},
                    mapTypeControl: true,
                    streetViewControl: true,
                    fullscreenControl: true,
                    zoomControl: true,
                    mapTypeId: "roadmap"
                }});
                
                // マーカーの追加
    """
    
    # マーカーを追加
    for i, marker in enumerate(markers):
        marker_lat = marker.get('lat')
        marker_lng = marker.get('lng')
        marker_title = marker.get('title', '').replace('"', '\\"')
        marker_info = marker.get('info', marker_title).replace('"', '\\"')
        marker_icon = marker.get('icon', '')
        icon_code = f'icon: "{marker_icon}",' if marker_icon else ''
        
        html += f"""
                const marker{i} = new google.maps.Marker({{
                    position: {{ lat: {marker_lat}, lng: {marker_lng} }},
                    map: map,
                    {icon_code}
                    title: "{marker_title}"
                }});
                
                const infowindow{i} = new google.maps.InfoWindow({{
                    content: "{marker_info}"
                }});
                
                marker{i}.addListener("click", () => {{
                    infowindow{i}.open({{
                        anchor: marker{i},
                        map,
                    }});
                }});
        """
    
    # クリックイベントのハンドラーを追加 (位置選択用)
    html += """
                // クリックイベント
                map.addListener("click", (mapsMouseEvent) => {
                    const latLng = mapsMouseEvent.latLng.toJSON();
                    window.parent.postMessage({
                        type: "map_click",
                        lat: latLng.lat,
                        lng: latLng.lng
                    }, "*");
                });
            }
        </script>
        <script async defer
            src="https://maps.googleapis.com/maps/api/js?key=""" + GOOGLE_MAPS_API_KEY + """&callback=initMap">
        </script>
    </body>
    </html>
    """
    return html

def main():
    st.title("トランクルーム検索")
    
    # セッション状態の初期化
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "selected_lat" not in st.session_state:
        st.session_state.selected_lat = 35.6812  # 東京駅の緯度
    if "selected_lng" not in st.session_state:
        st.session_state.selected_lng = 139.7671  # 東京駅の経度
    if "map_clicked" not in st.session_state:
        st.session_state.map_clicked = False
    
    # 認証済みでない場合はログイン画面を表示
    if not st.session_state.authenticated:
        show_login_page()
        return
    
    # 認証済みの場合は検索画面を表示
    st.success(f"ログイン中: {st.session_state.user['email']}")
        
    # 検索方法の選択
    search_method = st.radio("検索方法を選択", ["住所で検索", "地図で選択"])
    
    if search_method == "住所で検索":
        # 住所入力による検索
        address = st.text_input("住所を入力", "東京都千代田区丸の内1-1")
        
        if st.button("検索"):
            with st.spinner("住所を検索しています..."):
                try:
                    # 住所から緯度経度を取得
                    geolocator = Nominatim(user_agent="trunkroom-app")
                    location = geolocator.geocode(address)
                    
                    if location:
                        st.session_state.selected_lat = location.latitude
                        st.session_state.selected_lng = location.longitude
                        
                        # 検索位置のマーカー
                        markers = [{
                            'lat': location.latitude,
                            'lng': location.longitude,
                            'title': '検索場所',
                            'info': f'<h3>検索場所</h3><p>{address}</p>',
                            'icon': 'https://maps.google.com/mapfiles/ms/icons/red-dot.png'
                        }]
                        
                        # Google Maps表示
                        st.subheader("検索場所")
                        map_html = create_google_map_html(
                            location.latitude, 
                            location.longitude, 
                            markers=markers, 
                            zoom=15
                        )
                        st.components.v1.html(map_html, height=500)
        
                        # 近隣施設を取得して表示
                        facilities = get_nearby_facilities(location.latitude, location.longitude)
                        display_facilities(facilities)
        
                        # 施設情報があれば地図に表示
                        if facilities:
                            # 施設のマーカーを作成
                            facility_markers = []
                            for facility in facilities:
                                if facility.get('latitude') and facility.get('longitude'):
                                    facility_markers.append({
                                        'lat': facility['latitude'],
                                        'lng': facility['longitude'],
                                        'title': facility['name'],
                                        'info': f'<h3>{facility["name"]}</h3><p>{facility["address"]}</p>',
                                        'icon': 'https://maps.google.com/mapfiles/ms/icons/blue-dot.png'
                                    })
                            
                            # 検索位置と施設の両方のマーカーを含む地図を表示
                            all_markers = markers + facility_markers
                            st.subheader("近隣施設マップ")
                            map_html = create_google_map_html(
                                location.latitude,
                                location.longitude,
                                markers=all_markers,
                                zoom=14
                            )
                            st.components.v1.html(map_html, height=600)
                    else:
                        st.error("入力された住所が見つかりませんでした。")
    except Exception as e:
                    st.error(f"住所検索中にエラーが発生しました: {str(e)}")
        
    else:  # 地図で選択
        st.write("地図上でクリックして場所を選択してください。")
        
        # 初期マーカー
        initial_marker = {
            'lat': st.session_state.selected_lat,
            'lng': st.session_state.selected_lng,
            'title': '選択場所',
            'icon': 'https://maps.google.com/mapfiles/ms/icons/red-dot.png'
        }
        
        # Google Maps表示（クリッカブル）
        map_html = create_google_map_html(
            st.session_state.selected_lat,
            st.session_state.selected_lng,
            markers=[initial_marker],
            zoom=13
        )
        
        # マップコンポーネントを表示し、クリックイベントを取得
        map_component = st.components.v1.html(map_html, height=500)
        if map_component:
            # クリックイベントがあれば位置を更新
            click_data = map_component.get("type")
            if click_data == "map_click":
                st.session_state.selected_lat = map_component.get("lat")
                st.session_state.selected_lng = map_component.get("lng")
                st.session_state.map_clicked = True
                st.experimental_rerun()
        
        # 手動で緯度経度を入力するオプション
        col1, col2 = st.columns(2)
        with col1:
            new_lat = st.number_input("緯度", value=st.session_state.selected_lat, format="%.6f")
        with col2:
            new_lng = st.number_input("経度", value=st.session_state.selected_lng, format="%.6f")
        
        if st.button("この位置で検索") or st.session_state.map_clicked:
            st.session_state.map_clicked = False
            st.session_state.selected_lat = new_lat
            st.session_state.selected_lng = new_lng
            
            # 選択位置のマーカー
            selected_marker = {
                'lat': new_lat,
                'lng': new_lng,
                'title': '選択場所',
                'info': f'<h3>選択場所</h3><p>緯度: {new_lat:.6f}, 経度: {new_lng:.6f}</p>',
                'icon': 'https://maps.google.com/mapfiles/ms/icons/red-dot.png'
            }
            
            # マップを再表示
            st.subheader("選択場所")
            map_html = create_google_map_html(
                new_lat,
                new_lng,
                markers=[selected_marker],
                zoom=15
            )
            st.components.v1.html(map_html, height=500)
            
            # 近隣施設を取得して表示
            facilities = get_nearby_facilities(new_lat, new_lng)
            display_facilities(facilities)
            
            # 施設情報があれば地図に表示
            if facilities:
                # 施設のマーカーを作成
                facility_markers = []
                for facility in facilities:
                    if facility.get('latitude') and facility.get('longitude'):
                        facility_markers.append({
                            'lat': facility['latitude'],
                            'lng': facility['longitude'],
                            'title': facility['name'],
                            'info': f'<h3>{facility["name"]}</h3><p>{facility["address"]}</p>',
                            'icon': 'https://maps.google.com/mapfiles/ms/icons/blue-dot.png'
                        })
                
                # 選択位置と施設の両方のマーカーを含む地図を表示
                all_markers = [selected_marker] + facility_markers
                st.subheader("近隣施設マップ")
                map_html = create_google_map_html(
                    new_lat,
                    new_lng,
                    markers=all_markers,
                    zoom=14
                )
                st.components.v1.html(map_html, height=600)
    
    # ログアウトボタン
    if st.sidebar.button("ログアウト"):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()

def show_login_page():
    """ログインおよび新規登録の画面を表示"""
    # タブで認証方法を切り替え
    tab1, tab2 = st.tabs(["ログイン", "新規登録"])
    
    with tab1:
        st.header("ログイン")
        login_email = st.text_input("メールアドレス", key="login_email")
        login_password = st.text_input("パスワード", type="password", key="login_password")
        
        if st.button("ログイン"):
            if login_email and login_password:
                with st.spinner("ログイン中..."):
                    try:
                        result = login(login_email, login_password)
                        if result.user:
                            st.session_state.authenticated = True
                            st.session_state.user = {
                                "id": result.user.id,
                                "email": result.user.email
                            }
                            st.success("ログインに成功しました！")
                            st.rerun()
                        else:
                            st.error("ログインに失敗しました。メールアドレスとパスワードを確認してください。")
    except Exception as e:
                        st.error(f"エラーが発生しました: {str(e)}")
            else:
                st.warning("メールアドレスとパスワードを入力してください。")
    
    with tab2:
        st.header("新規登録")
        signup_email = st.text_input("メールアドレス", key="signup_email")
        signup_password = st.text_input("パスワード", type="password", key="signup_password")
        signup_password_confirm = st.text_input("パスワード（確認）", type="password", key="signup_password_confirm")
        
        if st.button("アカウント作成"):
            if signup_email and signup_password and signup_password_confirm:
                if signup_password != signup_password_confirm:
                    st.error("パスワードが一致しません。")
                else:
                    with st.spinner("アカウント作成中..."):
                        try:
                            result = signup(signup_email, signup_password)
                            if result.user:
                                st.session_state.authenticated = True
                                st.session_state.user = {
                                    "id": result.user.id,
                                    "email": result.user.email
                                }
                                st.success("アカウントが作成されました！")
                                st.rerun()
                            else:
                                st.error("アカウント作成に失敗しました。")
    except Exception as e:
                            st.error(f"エラーが発生しました: {str(e)}")
            else:
                st.warning("すべての項目を入力してください。")

if __name__ == "__main__":
    main()
