import os
import sys
import pandas as pd
import urllib.parse
import requests

# プロジェクトのルートパスを動的に計算
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, root_path)

import streamlit as st
from src.auth.auth import login, signup, get_supabase_client
from geopy.geocoders import Nominatim

# Google Maps APIキーを環境変数から取得（緯度経度変換用）
from dotenv import load_dotenv
load_dotenv()

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
    """施設のリストを表示する（一覧表示形式）"""
    if not facilities:
        st.info("近くの施設が見つかりませんでした。")
        return
        
    st.subheader(f"近くの施設 ({len(facilities)}件)")
    
    # 表示するデータの準備
    data = []
    for facility in facilities:
        # アメニティ情報
        amenities = []
        if facility.get('has_elevator'):
            amenities.append("✓")
        else:
            amenities.append("")
            
        if facility.get('has_security'):
            amenities.append("✓")
        else:
            amenities.append("")
            
        if facility.get('has_airconditioner'):
            amenities.append("✓")
        else:
            amenities.append("")
        
        # 距離を表示（kmに変換）
        distance = ""
        if facility.get('distance'):
            distance = f"{facility['distance']:.1f}km"
        
        # データ行の作成
        row = {
            "物件名": facility['name'],
            "住所": facility['address'],
            "最低料金": f"{facility.get('min_price', '---'):,}円～" if facility.get('min_price') else "---",
            "最小サイズ": f"{facility.get('min_size', '---')}㎡～" if facility.get('min_size') else "---",
            "エレベーター": amenities[0],
            "セキュリティ": amenities[1],
            "空調": amenities[2],
            "距離": distance,
        }
        data.append(row)
    
    # DataFrameに変換
    df = pd.DataFrame(data)
    
    # データフレームを表示
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "物件名": st.column_config.TextColumn("物件名", width="medium"),
            "住所": st.column_config.TextColumn("住所", width="large"),
            "最低料金": st.column_config.TextColumn("最低料金", width="small"),
            "最小サイズ": st.column_config.TextColumn("最小サイズ", width="small"),
            "エレベーター": st.column_config.CheckboxColumn("エレベーター", width="small"),
            "セキュリティ": st.column_config.CheckboxColumn("セキュリティ", width="small"), 
            "空調": st.column_config.CheckboxColumn("空調", width="small"),
            "距離": st.column_config.TextColumn("距離", width="small")
        },
        hide_index=True
    )

def geocode_with_google(address):
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    address_encoded = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address_encoded}&key={api_key}"
    
    response = requests.get(url)
    data = response.json()
    
    if data["status"] == "OK":
        location = data["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    return None

def display_map(lat, lng, zoom=13, facilities=None):
    """地図を表示する関数"""
    if facilities:
        # 施設の位置を含めた地図を表示
        st.subheader("施設の位置")
        map_data = []
        
        # 検索位置
        map_data.append({
            'lat': lat,
            'lon': lng,
            'size': 10
        })
        
        # 施設の位置
        for facility in facilities:
            if facility.get('latitude') and facility.get('longitude'):
                map_data.append({
                    'lat': facility['latitude'],
                    'lon': facility['longitude'],
                    'size': 6
                })
        
        # 地図用データフレーム作成
        df_facilities = pd.DataFrame({
            'lat': [item['lat'] for item in map_data],
            'lon': [item['lon'] for item in map_data],
            'size': [8 if i == 0 else 6 for i in range(len(map_data))]
        })
        
        # 地図表示
        st.map(df_facilities, zoom=zoom)
    else:
        # 検索位置のみの地図を表示
        st.subheader("現在の場所")
        df_map = pd.DataFrame({
            'lat': [lat],
            'lon': [lng],
            'size': [5]
        })
        st.map(df_map, zoom=zoom)

def main():
    st.title("トランクルーム検索")
    
    # セッション変数の初期化
    if "selected_lat" not in st.session_state:
        st.session_state.selected_lat = 35.6812  # 東京駅の緯度
    if "selected_lng" not in st.session_state:
        st.session_state.selected_lng = 139.7671  # 東京駅の経度
    if "search_performed" not in st.session_state:
        st.session_state.search_performed = False
    if "found_facilities" not in st.session_state:
        st.session_state.found_facilities = []
    
    # 住所入力による検索
    address = st.text_input("住所・建物名などを入力", "東京都千代田区丸の内1-1")
    
    # 検索ボタン処理
    if st.button("検索"):
        with st.spinner("住所を検索しています..."):
            try:
                # まずGoogleのAPIで試す（番地まで詳細に対応）
                location_data = geocode_with_google(address)
                
                if location_data:
                    lat, lng = location_data
                    st.session_state.selected_lat = lat
                    st.session_state.selected_lng = lng
                else:
                    # Google APIで失敗したらNominatimでバックアップ
                    geolocator = Nominatim(user_agent="trunkroom-app")
                    location = geolocator.geocode(address)
                    
                    if location:
                        st.session_state.selected_lat = location.latitude
                        st.session_state.selected_lng = location.longitude
                    else:
                        st.error("入力された住所が見つかりませんでした。")
                        st.stop()
                
                # 検索済みフラグを立てる
                st.session_state.search_performed = True
                
                # 近隣施設を取得してセッション状態に保存
                st.session_state.found_facilities = get_nearby_facilities(
                    st.session_state.selected_lat, 
                    st.session_state.selected_lng
                )
                
                # 再描画のためにリロード
                st.rerun()
                
            except Exception as e:
                st.error(f"住所検索中にエラーが発生しました: {str(e)}")
    
    # 検索結果の表示（検索後の場合）
    if st.session_state.search_performed:
        # 検索した施設を表示
        display_facilities(st.session_state.found_facilities)
        
        # 検索位置と施設の位置を同じ地図に表示
        display_map(
            st.session_state.selected_lat, 
            st.session_state.selected_lng, 
            zoom=12, 
            facilities=st.session_state.found_facilities
        )
    else:
        # 初期表示（検索前の場合）
        # デフォルトで近隣施設も表示
        default_facilities = get_nearby_facilities(
            st.session_state.selected_lat, 
            st.session_state.selected_lng
        )
        
        # 施設情報を表示
        if default_facilities:
            display_facilities(default_facilities)
        
        # 東京駅とデフォルト施設を同じ地図に表示
        display_map(
            st.session_state.selected_lat, 
            st.session_state.selected_lng, 
            zoom=12, 
            facilities=default_facilities
        )

if __name__ == "__main__":
    main()
