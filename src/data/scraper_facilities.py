import os
import sys
import requests
from bs4 import BeautifulSoup
import datetime
import time
import json
import argparse
import pandas as pd

# プロジェクトのルートパスを動的に計算
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, root_path)

from src.auth.auth import get_supabase_client

# 東京23区の区名と対応するURL部分
TOKYO_23_WARDS = {
    "千代田区": "chiyoda-city",
    "中央区": "chuo-city",
    "港区": "minato-city",
    "新宿区": "shinjuku-city",
    "文京区": "bunkyo-city",
    "台東区": "taito-city",
    "墨田区": "sumida-city",
    "江東区": "koto-city",
    "品川区": "shinagawa-city",
    "目黒区": "meguro-city",
    "大田区": "ota-city",
    "世田谷区": "setagaya-city",
    "渋谷区": "shibuya-city",
    "中野区": "nakano-city",
    "杉並区": "suginami-city",
    "豊島区": "toshima-city",
    "北区": "kita-city",
    "荒川区": "arakawa-city",
    "板橋区": "itabashi-city",
    "練馬区": "nerima-city",
    "足立区": "adachi-city",
    "葛飾区": "katsushika-city",
    "江戸川区": "edogawa-city"
}

def scrape_website(url):
    """
    指定されたURLからHTMLを取得し、BeautifulSoupオブジェクトを返す
    """
    try:
        # User-Agentを設定してブロックを回避
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # エラーがあれば例外を発生させる
        
        # HTMLをBeautifulSoupでパース
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup
    
    except requests.exceptions.RequestException as e:
        print(f"スクレイピング中にエラーが発生しました: {str(e)}")
        return None

def save_to_database(data, table_name="storage_facilities"):
    """
    スクレイピングしたデータをデータベースに保存
    """
    try:
        supabase = get_supabase_client()
        
        # データに現在時刻を追加
        data["created_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        
        # データをリストで渡す
        result = supabase.table(table_name).insert([data]).execute()
        return result
    
    except Exception as e:
        print(f"データベース保存中にエラーが発生しました: {str(e)}")
        return None

def scrape_trunkroom_properties(ward_url_part, limit=None, verbose=False):
    """特定の区のトランクルーム物件情報をスクレイピングする"""
    base_url = f"https://www.japantrunkroom.com/tokyo/{ward_url_part}/"
    properties = []
    
    if verbose:
        print(f"URLをスクレイピング中: {base_url}")
    
    try:
        soup = scrape_website(base_url)
        if not soup:
            return properties
        
        # 物件データを含むdiv要素を取得（spec クラス）
        property_elements = soup.select("div.spec")
        
        if verbose:
            print(f"{len(property_elements)}件の物件情報を検出しました")
        
        # 制限数を設定
        if limit is not None and limit > 0:
            property_elements = property_elements[:limit]
            if verbose:
                print(f"物件数を{limit}件に制限します")
        
        for element in property_elements:
            try:
                # データ属性から物件IDを取得
                building_id = element.get('data-building_id', '')
                
                if verbose:
                    print(f"物件ID {building_id} を処理中...")
                
                # 物件コンテナの検索方法を変更
                property_container = element.find_parent('div', class_='detailListContents')
                if not property_container and verbose:
                    print(f"物件ID {building_id} のコンテナが見つかりません")
                    continue
                
                # 物件名取得 - 修正
                # h3要素を直接探す（親要素を特定せず）
                h3_element = property_container.find_previous('h3') if property_container else None
                
                # h3から物件名を抽出
                name = "不明"
                if h3_element:
                    # aタグがある場合はそこから取得（物件名）
                    a_element = h3_element.find('a')
                    if a_element:
                        name = a_element.text.strip()
                    # aタグがなければh3のテキスト全体を取得
                    else:
                        name = h3_element.text.strip()
                
                # ========= 改善: 価格情報抽出 ==========
                fee_element = element.select_one("dl.fee")
                min_price, max_price = 0, 0
                if fee_element:
                    # spanタグから直接価格テキストを取得
                    price_span = fee_element.select_one("dd span")
                    if price_span:
                        price_text = price_span.text.strip()
                        min_price, max_price = extract_price_range(price_text)
                
                # ========= 改善: 広さ情報抽出 ==========
                breadth_element = element.select_one("dl.breadth")
                min_size, max_size = 0.0, 0.0
                if breadth_element:
                    # spanタグから直接サイズテキストを取得
                    size_span = breadth_element.select_one("dd span")
                    if size_span:
                        size_text = size_span.text.strip()
                        min_size, max_size = extract_size_range(size_text)
                
                # ========= 改善: 住所情報抽出 ==========
                address_element = element.select_one("dl.address")
                address_text = ""
                if address_element:
                    # spanタグから直接住所テキストを取得
                    address_span = address_element.select_one("dd span")
                    if address_span:
                        address_text = address_span.text.strip()
                
                # ========= 改善: アクセス情報抽出 ==========
                access_element = element.select_one("dl.access")
                access_text = ""
                if access_element:
                    # pタグから直接アクセステキストを取得
                    access_p = access_element.select_one("dd p")
                    if access_p:
                        access_text = access_p.text.strip()
                
                # 屋内・屋外の情報取得 - 修正
                location_type = "不明"
                detail_list_title = property_container.find_previous('div', class_='detailListTitle') if property_container else None
                if detail_list_title:
                    type_element = detail_list_title.find('div', class_='type')
                    if type_element:
                        type_classes = type_element.get('class', [])
                        if 'indoor' in type_classes:
                            location_type = "屋内"
                        elif 'outdoor' in type_classes:
                            location_type = "屋外"
                        else:
                            location_type = type_element.get_text(strip=True)
                
                # HTMLの構造に合わせて特徴情報の取得方法を修正
                option_div = None
                if property_container:
                    # 現在の方法
                    option_div = property_container.find('div', class_='detailListOption')
                    
                    # 見つからない場合はセレクタを使用
                    if not option_div:
                        option_div = property_container.select_one('div.detailListOption')
                    
                    # それでも見つからない場合は親要素全体から検索
                    if not option_div and property_container.parent:
                        option_div = property_container.parent.find('div', class_='detailListOption')

                features_list = None
                if option_div:
                    features_list = option_div.find('ul')

                # 見つからなかったらデフォルト値を設定
                has_alltime = False
                has_parking = False
                has_elevator = False
                has_airconditioning = False
                has_ventilator = False
                has_security = False
                
                # 特徴リストがあれば処理
                if features_list:
                    # 各特徴を確認
                    for feature in features_list.find_all('li'):
                        feature_class = feature.get('class', [])
                        if feature_class:
                            # alltime（24時間利用可能）
                            if 'alltime' in feature_class:
                                has_alltime = 'disabled' not in feature_class
                            # parking（駐車場）
                            elif 'parking' in feature_class:
                                has_parking = 'disabled' not in feature_class
                            # elevator（エレベーター）
                            elif 'elevator' in feature_class:
                                has_elevator = 'disabled' not in feature_class
                            # airconditioner（空調設備）
                            elif 'airconditioner' in feature_class:
                                has_airconditioning = 'disabled' not in feature_class
                            # ventilator（換気設備）
                            elif 'ventilator' in feature_class:
                                has_ventilator = 'disabled' not in feature_class
                            # security（防犯設備）
                            elif 'security' in feature_class:
                                has_security = 'disabled' not in feature_class
                
                property_data = {
                    "name": name,
                    "address": address_text,
                    "location_type": location_type,
                    "access": access_text,
                    "min_size": min_size,
                    "max_size": max_size,
                    "min_price": min_price,
                    "max_price": max_price,
                    "has_alltime": has_alltime,
                    "has_parking": has_parking,
                    "has_elevator": has_elevator,
                    "has_airconditioner": has_airconditioning,
                    "has_ventilator": has_ventilator,
                    "has_security": has_security
                }
                
                properties.append(property_data)
                
                if verbose:
                    print(f"物件「{name}」の情報を取得しました")
                
            except Exception as e:
                if verbose:
                    import traceback
                    print(f"物件情報の抽出中にエラー: {str(e)}")
                    print(traceback.format_exc())
                continue
        
        return properties
        
    except Exception as e:
        if verbose:
            import traceback
            print(f"スクレイピング中にエラー: {str(e)}")
            print(traceback.format_exc())
        return properties

def extract_price_range(price_text):
    """価格範囲テキストから最小・最大価格を抽出
    例: "4,400円/月～24,200円/月" → (4400, 24200)
    """
    try:
        import re
        # 円/月の前の数字を抽出
        match = re.search(r'([0-9,]+)円/月～([0-9,]+)円/月', price_text)
        if match:
            min_price = int(match.group(1).replace(',', ''))
            max_price = int(match.group(2).replace(',', ''))
            return min_price, max_price
        
        # 単一価格の場合
        match = re.search(r'([0-9,]+)円/月', price_text)
        if match:
            price = int(match.group(1).replace(',', ''))
            return price, price
        
        return 0, 0
    except:
        return 0, 0

def extract_size_range(size_text):
    """サイズ範囲テキストから最小・最大サイズを抽出
    例: "1.01m²～4.32m²" → (1.01, 4.32)
    """
    try:
        import re
        # 範囲表記の場合
        match = re.search(r'([0-9.]+)m²～([0-9.]+)m²', size_text)
        if match:
            min_size = float(match.group(1))
            max_size = float(match.group(2))
            return min_size, max_size
        
        # 単一サイズの場合
        match = re.search(r'([0-9.]+)m²', size_text)
        if match:
            size = float(match.group(1))
            return size, size
        
        return 0.0, 0.0
    except:
        return 0.0, 0.0

def scrape_all_tokyo_wards(limit_per_ward=None, verbose=False, save_to_db=False):
    """東京23区すべての区のトランクルーム物件情報をスクレイピング"""
    all_properties = []
    
    for ward_name, ward_url_part in TOKYO_23_WARDS.items():
        print(f"{ward_name}のスクレイピングを開始...")
        ward_properties = scrape_trunkroom_properties(ward_url_part, limit=limit_per_ward, verbose=verbose)
        
        print(f"- {len(ward_properties)}件の物件を取得しました")
        
        # データベースに直接保存するオプション
        if save_to_db and ward_properties:
            success_count = 0
            print(f"- データベースに保存中...")
            for prop in ward_properties:
                result = save_to_database(prop)
                if result:
                    success_count += 1
            print(f"- {success_count}/{len(ward_properties)}件のデータをDBに保存しました")
        
        all_properties.extend(ward_properties)
        
        # サーバー負荷軽減のための待機
        time.sleep(2)
    
    return all_properties

def save_to_csv(properties, filename=None):
    """物件情報をCSVファイルに保存"""
    if not properties:
        print("保存するデータがありません")
        return
    
    if not filename:
        today = datetime.date.today().strftime("%Y%m%d")
        filename = f"trunkroom_data_{today}.csv"
    
    df = pd.DataFrame(properties)
    df.to_csv(filename, index=False, encoding='utf-8')
    print(f"{len(properties)}件のデータを{filename}に保存しました")
    return filename

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='トランクルーム物件情報スクレイパー')
    parser.add_argument('--ward', help='特定の区のみスクレイピング（例：中央区）')
    parser.add_argument('--limit', type=int, help='各区から取得する物件数の上限')
    parser.add_argument('--verbose', action='store_true', help='詳細なログを出力')
    parser.add_argument('--db', action='store_true', help='データベースに直接保存')
    parser.add_argument('--csv', action='store_true', help='結果をCSVに保存')
    parser.add_argument('--output', help='CSVファイルの出力パス')
    
    args = parser.parse_args()
    
    # 特定の区だけスクレイピング
    if args.ward:
        if args.ward in TOKYO_23_WARDS:
            print(f"{args.ward}の物件情報をスクレイピングします...")
            properties = scrape_trunkroom_properties(
                TOKYO_23_WARDS[args.ward], 
                limit=args.limit, 
                verbose=args.verbose
            )
            
            print(f"{len(properties)}件の物件情報を取得しました")
            
            # データベースに保存
            if args.db:
                success_count = 0
                print("データベースに保存中...")
                for prop in properties:
                    result = save_to_database(prop)
                    if result:
                        success_count += 1
                print(f"{success_count}/{len(properties)}件のデータをDBに保存しました")
            
            # CSVに保存
            if args.csv:
                output_file = args.output or f"trunkroom_{TOKYO_23_WARDS[args.ward]}_{datetime.date.today().strftime('%Y%m%d')}.csv"
                save_to_csv(properties, output_file)
        else:
            print(f"エラー: {args.ward}は有効な区名ではありません")
            print(f"有効な区名: {', '.join(TOKYO_23_WARDS.keys())}")
    
    # 全区スクレイピング
    else:
        print("東京23区すべての物件情報をスクレイピングします...")
        properties = scrape_all_tokyo_wards(
            limit_per_ward=args.limit, 
            verbose=args.verbose,
            save_to_db=args.db
        )
        
        print(f"合計{len(properties)}件の物件情報を取得しました")
        
        # CSVに保存
        if args.csv:
            output_file = args.output or f"trunkroom_all_wards_{datetime.date.today().strftime('%Y%m%d')}.csv"
            save_to_csv(properties, output_file)
