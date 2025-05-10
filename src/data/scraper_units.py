import os
import sys
import datetime
import time
import json
import argparse
import pandas as pd
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import re

# プロジェクトのルートパスを動的に計算
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, root_path)

from src.auth.auth import get_supabase_client

# 千代田区のURLパート
CHIYODA_URL_PART = "chiyoda-city"

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

def save_unit_to_database(data, facility_uuid, table_name="storage_units"):
    """
    スクレイピングした区画データをデータベースに保存
    """
    try:
        supabase = get_supabase_client()
        
        # テーブル構造に合わせたデータ形式に変換
        formatted_data = {
            "facility_id": facility_uuid,  # 物件テーブルから取得したUUID
            "size_sqm": data["size"],
            "rent": data["price"],
            "is_available": data["is_vacant"]
        }
        
        # データをリストで渡す
        result = supabase.table(table_name).insert([formatted_data]).execute()
        return result
    
    except Exception as e:
        print(f"データベース保存中にエラー: {str(e)}")
        return None

def extract_building_ids_from_ward_page(browser, ward_url_part, verbose=False):
    """
    特定の区ページから物件IDのリストを抽出
    """
    building_ids = []
    ward_url = f"https://www.japantrunkroom.com/tokyo/{ward_url_part}/"
    
    page = browser.new_page()
    
    if verbose:
        print(f"{ward_url_part}のページにアクセス中: {ward_url}")
    
    # ページへアクセス
    page.goto(ward_url, wait_until="domcontentloaded", timeout=60000)
    
    # 物件リストを含む要素を待機
    page.wait_for_selector(".detailListContents", timeout=10000)
    
    # 物件リンクを全て取得
    facility_links = page.query_selector_all(".detailListTitle h3 a")
    
    if verbose:
        print(f"{len(facility_links)}件の物件リンクを検出")
    
    for link in facility_links:
        try:
            # href属性からbuilding_idを抽出
            href = link.get_attribute("href")
            
            # "/b-19741/?flow=2" から "19741" を抽出するパターン
            match = re.search(r'/b-(\d+)(?:/|\?)', href)
            if match:
                building_id = match.group(1)
                name = link.get_attribute("title") or link.inner_text().strip()
                
                building_ids.append({
                    "building_id": building_id,
                    "name": name,
                    "url": f"https://www.japantrunkroom.com/b-{building_id}/"
                })
        
        except Exception as e:
            if verbose:
                print(f"物件リンクの処理中にエラー: {str(e)}")
                print(f"  href: {href if 'href' in locals() else 'undefined'}")
    
    if verbose:
        print(f"{len(building_ids)}件の物件IDを取得しました")
        for i, bid in enumerate(building_ids[:3]):  # 最初の3件だけ表示
            print(f"  {i+1}. ID: {bid['building_id']}, 名前: {bid['name']}")
        if len(building_ids) > 3:
            print(f"  ... 他 {len(building_ids)-3} 件")
    
    return building_ids

def scrape_facility_units_with_context(facility_info, context, verbose=False):
    """
    物件の個別ページをスクレイピングして、区画情報を取得する
    既存のブラウザコンテキストを利用する版
    """
    units = []
    page = context.new_page()
    
    try:
        url = facility_info['url']
        
        if verbose:
            print(f"物件ページにアクセス中: {url}")
        
        # ページへアクセス
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # 表形式の区画情報を取得
        table = page.query_selector("table.tableInfo.feeList")
        if not table:
            # 代替セレクタを試す
            table = page.query_selector("table.feeList")
            if not table:
                table = page.query_selector("table.tableInfo")

        if table:
            # データが見つかったので処理
            table_rows = page.query_selector_all("table.tableInfo.feeList tbody tr")
            if not table_rows or len(table_rows) == 0:
                table_rows = page.query_selector_all("table tbody tr")
            
            if verbose:
                print(f"表形式で{len(table_rows)}件の区画情報を検出しました")
            
            for row in table_rows:
                try:
                    # 区画情報の抽出処理（現行のコードを流用）
                    unit_number = row.query_selector("th")
                    unit_number_text = unit_number.inner_text().strip() if unit_number else "不明"
                    
                    # 広さ
                    size_td = row.query_selector("td.breadth")
                    size_text = size_td.inner_text().strip() if size_td else ""
                    size_value = extract_size(size_text)
                    
                    # 料金
                    price_td = row.query_selector("td.fee")
                    price_text = price_td.inner_text().strip() if price_td else ""
                    price_value = extract_price(price_text)
                    
                    # 空室状況の判定を改善
                    is_vacant = False
                    inquiry_td = row.query_selector("td.btn")
                    if inquiry_td:
                        # メールリンクの存在で判定
                        mail_link = inquiry_td.query_selector("a.mail")
                        if mail_link:
                            is_vacant = True
                        
                        # テキストでも判定
                        if "満室のため" in inquiry_td.inner_text():
                            is_vacant = False
                    
                    unit_data = {
                        "building_id": facility_info['building_id'],
                        "facility_name": facility_info['name'],
                        "unit_number": unit_number_text,
                        "size": size_value,
                        "price": price_value,
                        "is_vacant": is_vacant,
                        "last_checked": datetime.datetime.now(datetime.UTC).isoformat()
                    }
                    
                    units.append(unit_data)
                    
                    if verbose:
                        status = "空室" if is_vacant else "満室"
                        print(f"  区画「{unit_number_text}」: {size_value}m², {price_value}円/月, {status}")
                
                except Exception as e:
                    if verbose:
                        print(f"区画情報の抽出中にエラー: {str(e)}")
                    continue
        
        # フォールバック処理
        elif not units:
            if verbose:
                print(f"表形式での取得に失敗したため、代替方法を試みます")
            
            # 追加のフォールバックロジックをここに実装...
    
    except Exception as e:
        if verbose:
            print(f"物件ページのスクレイピング中にエラー: {str(e)}")
            import traceback
            print(traceback.format_exc())
    
    finally:
        page.close()
    
    return units

def extract_size(size_text):
    """サイズテキストから数値を抽出（例: "11.55m²" → 11.55）"""
    try:
        import re
        match = re.search(r'(\d+(?:\.\d+)?)m²', size_text)
        if match:
            return float(match.group(1))
        return 0.0
    except:
        return 0.0

def extract_price(price_text):
    """価格テキストから数値を抽出（例: "139,800円/月" → 139800）"""
    try:
        import re
        match = re.search(r'(\d+(?:,\d+)*)円', price_text)
        if match:
            return int(match.group(1).replace(',', ''))
        return 0
    except:
        return 0

def save_to_csv(units, filename=None):
    """区画情報をCSVファイルに保存"""
    if not units:
        print("保存するデータがありません")
        return
    
    if not filename:
        today = datetime.date.today().strftime("%Y%m%d")
        filename = f"trunkroom_units_chiyoda_{today}.csv"
    
    df = pd.DataFrame(units)
    df.to_csv(filename, index=False, encoding='utf-8')
    print(f"{len(units)}件の区画データを{filename}に保存しました")
    return filename

def find_facility_by_building_id_or_name(facility_info, verbose=False):
    """
    元の物件ID、または物件名で既存の物件を検索
    新規作成は行わない
    """
    try:
        supabase = get_supabase_client()
        building_id = facility_info['building_id']
        
        # 方法1: accessフィールドから物件IDを検索
        result = supabase.table("storage_facilities")\
                        .select("id")\
                        .like("access", f"%物件ID: {building_id}%")\
                        .execute()
        
        # 見つかった場合はIDを返す
        if result and result.data and len(result.data) > 0:
            if verbose:
                print(f"  物件ID {building_id} に対応する物件を見つけました (UUID: {result.data[0]['id']})")
            return result.data[0]["id"]
        
        # 方法2: 物件名で検索（部分一致）
        facility_name = facility_info['name']
        result = supabase.table("storage_facilities")\
                        .select("id")\
                        .like("name", f"%{facility_name}%")\
                        .execute()
        
        # 見つかった場合はIDを返す
        if result and result.data and len(result.data) > 0:
            if verbose:
                print(f"  物件名 '{facility_name}' に一致する物件を見つけました (UUID: {result.data[0]['id']})")
            return result.data[0]["id"]
        
        # 見つからなかった場合
        if verbose:
            print(f"  物件ID {building_id} または名前 '{facility_name}' に一致する物件が見つかりませんでした")
        return None
    
    except Exception as e:
        print(f"物件情報の検索中にエラー: {str(e)}")
        return None

def save_facility_and_get_id(facility_info):
    """
    物件情報を保存せず、既存のIDを検索して返すだけ
    """
    print("WARNING: このスクリプトでは物件の新規追加は行いません")
    return find_facility_uuid_by_building_id(facility_info['building_id'])

def process_chiyoda_units(limit=None, verbose=False, save_to_db=False, headless=True):
    """千代田区の物件を処理して区画情報を取得"""
    all_units = []
    facility_success = 0
    facility_error = 0
    
    # ブラウザは一度だけ起動
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        try:
            # 千代田区ページから物件IDを取得
            if verbose:
                print("千代田区の物件IDを取得中...")
            
            facilities = extract_building_ids_from_ward_page(browser, CHIYODA_URL_PART, verbose=verbose)
            
            if not facilities:
                print("千代田区で物件が見つかりませんでした")
                return all_units, 0, 0
            
            print(f"千代田区で{len(facilities)}件の物件を発見")
            
            # 制限がある場合
            if limit is not None and limit > 0:
                facilities = facilities[:limit]
                print(f"物件数を{limit}件に制限します")
            
            # 各物件をスクレイピング
            for i, facility in enumerate(facilities):
                if verbose:
                    print(f"物件 {i+1}/{len(facilities)}: 「{facility['name']}」のスクレイピングを開始...")
                
                try:
                    # 既存の物件を検索するのみ（新規作成はしない）
                    facility_uuid = find_facility_uuid_by_building_id(facility['building_id'])
                    if not facility_uuid:
                        if verbose:
                            print(f"  対応する物件が見つからないため、この物件はスキップします: {facility['name']}")
                        facility_error += 1
                        continue
                    
                    # 既存のコンテキストを利用して区画情報を取得
                    units = scrape_facility_units_with_context(facility, context, verbose=verbose)
                    
                    if units:
                        facility_success += 1
                        all_units.extend(units)
                        
                        # データベースに区画情報を保存
                        if save_to_db:
                            db_success = 0
                            for unit in units:
                                result = save_unit_to_database(unit, facility_uuid)
                                if result:
                                    db_success += 1
                            
                            if verbose:
                                print(f"  {db_success}/{len(units)}件の区画情報をDBに保存しました")
                    else:
                        facility_error += 1
                        if verbose:
                            print(f"  区画情報が取得できませんでした")
                
                except Exception as e:
                    facility_error += 1
                    if verbose:
                        print(f"物件処理中にエラー: {str(e)}")
                        import traceback
                        print(traceback.format_exc())
                
                # サーバー負荷軽減のための待機
                time.sleep(2)
                
        finally:
            browser.close()
    
    return all_units, facility_success, facility_error

def process_all_tokyo_wards(wards=None, limit_per_ward=None, verbose=False, save_to_db=False, headless=True):
    """東京23区（または指定した区）の物件を処理して区画情報を取得"""
    all_units = []
    ward_results = {}
    
    # 処理する区を決定（指定がなければ全23区）
    if wards is None:
        wards = TOKYO_23_WARDS
    else:
        # 指定された区名からURLパートを取得
        wards = {ward: TOKYO_23_WARDS.get(ward) for ward in wards if ward in TOKYO_23_WARDS}
    
    # ブラウザは一度だけ起動
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        try:
            # 各区ごとに処理
            for ward_name, ward_url_part in wards.items():
                if verbose:
                    print(f"\n=== {ward_name}の処理を開始 ===")
                
                # 区ページから物件IDを取得
                facilities = extract_building_ids_from_ward_page(browser, ward_url_part, verbose=verbose)
                
                if not facilities:
                    if verbose:
                        print(f"{ward_name}で物件が見つかりませんでした")
                    ward_results[ward_name] = {"success": 0, "error": 0, "units": 0}
                    continue
                
                print(f"{ward_name}で{len(facilities)}件の物件を発見")
                
                # 制限がある場合
                if limit_per_ward is not None and limit_per_ward > 0:
                    facilities = facilities[:limit_per_ward]
                    print(f"物件数を{limit_per_ward}件に制限します")
                
                # 各物件をスクレイピング
                ward_success = 0
                ward_error = 0
                ward_units = []
                
                for i, facility in enumerate(facilities):
                    if verbose:
                        print(f"物件 {i+1}/{len(facilities)}: 「{facility['name']}」のスクレイピングを開始...")
                    
                    try:
                        # 既存の物件を検索するのみ（新規作成はしない）
                        facility_uuid = find_facility_uuid_by_building_id(facility['building_id'])
                        if not facility_uuid:
                            if verbose:
                                print(f"  対応する物件が見つからないため、この物件はスキップします: {facility['name']}")
                            ward_error += 1
                            continue
                        
                        # 以下は既存処理
                        units = scrape_facility_units_with_context(facility, context, verbose=verbose)
                        
                        if units:
                            ward_success += 1
                            ward_units.extend(units)
                            all_units.extend(units)
                            
                            # データベースに保存
                            if save_to_db:
                                db_success = 0
                                for unit in units:
                                    result = save_unit_to_database(unit, facility_uuid)
                                    if result:
                                        db_success += 1
                                
                                if verbose:
                                    print(f"  {db_success}/{len(units)}件の区画情報をDBに保存しました")
                        else:
                            ward_error += 1
                            if verbose:
                                print(f"  区画情報が取得できませんでした")
                    
                    except Exception as e:
                        ward_error += 1
                        if verbose:
                            print(f"物件処理中にエラー: {str(e)}")
                            import traceback
                            print(traceback.format_exc())
                    
                    # サーバー負荷軽減のための待機
                    time.sleep(3)  # 区ごとの処理は少し長めの間隔を
                
                # 区の結果を記録
                ward_results[ward_name] = {
                    "success": ward_success, 
                    "error": ward_error, 
                    "units": len(ward_units)
                }
                
                if verbose:
                    print(f"{ward_name}の処理完了: 成功={ward_success}, 失敗={ward_error}, 合計区画数={len(ward_units)}")
                
                # 区ごとにCSVに保存（オプション）
                # save_to_csv(ward_units, f"trunkroom_units_{ward_url_part}_{datetime.date.today().strftime('%Y%m%d')}.csv")
                
                # 区と区の間の待機
                time.sleep(5)
                
        finally:
            browser.close()
    
    return all_units, ward_results

def find_facility_uuid_by_building_id(building_id):
    """
    元の物件IDからUUIDを検索（拡張版）
    """
    try:
        supabase = get_supabase_client()
        
        # 方法1: accessフィールドから物件IDを検索
        result = supabase.table("storage_facilities")\
                        .select("id")\
                        .like("access", f"%物件ID: {building_id}%")\
                        .execute()
        
        # 見つかった場合はIDを返す
        if result and result.data and len(result.data) > 0:
            return result.data[0]["id"]
            
        # 追加：ID自体で検索
        result = supabase.table("storage_facilities")\
                        .select("id")\
                        .eq("building_id_original", building_id)\
                        .execute()
                        
        if result and result.data and len(result.data) > 0:
            return result.data[0]["id"]
        
        return None
    
    except Exception as e:
        print(f"物件情報の検索中にエラー: {str(e)}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='東京都内のトランクルーム区画情報スクレイパー')
    parser.add_argument('--building_id', help='特定の物件IDのみをスクレイピング')
    parser.add_argument('--ward', help='特定の区のみを処理（例：千代田区,中央区）')
    parser.add_argument('--all_wards', action='store_true', help='東京23区全てを処理')
    parser.add_argument('--limit', type=int, help='1区あたりの取得物件数上限')
    parser.add_argument('--verbose', action='store_true', help='詳細なログを出力')
    parser.add_argument('--db', action='store_true', help='データベースに直接保存')
    parser.add_argument('--csv', action='store_true', help='結果をCSVに保存')
    parser.add_argument('--output', help='CSVファイルの出力パス')
    parser.add_argument('--visible', action='store_true', help='ブラウザを表示して実行')
    
    args = parser.parse_args()
    headless = not args.visible
    
    # 特定の物件IDが指定された場合
    if args.building_id:
        facility_info = {
            'name': f"物件ID:{args.building_id}",
            'building_id': args.building_id,
            'url': f"https://www.japantrunkroom.com/b-{args.building_id}/"
        }
        
        print(f"物件ID:{args.building_id}の区画情報をスクレイピングします...")
        
        # 1つの物件の場合も同じ方法で処理
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            
            try:
                units = scrape_facility_units_with_context(
                    facility_info, 
                    context,
                    verbose=args.verbose
                )
                
                print(f"{len(units)}件の区画情報を取得しました")
                
                # データベースに保存
                if args.db and units:
                    # 既存の物件IDを検索
                    facility_uuid = find_facility_uuid_by_building_id(args.building_id)
                    if not facility_uuid:
                        print(f"エラー: 物件ID {args.building_id} に対応する物件情報がデータベースに存在しません")
                        print("先に scraper_facilities.py を実行して物件情報を登録してください")
                    else:
                        success_count = 0
                        print("データベースに保存中...")
                        for unit in units:
                            result = save_unit_to_database(unit, facility_uuid)
                            if result:
                                success_count += 1
                        print(f"{success_count}/{len(units)}件のデータをDBに保存しました")
                
                # CSVに保存
                if args.csv and units:
                    output_file = args.output or f"trunkroom_units_{args.building_id}_{datetime.date.today().strftime('%Y%m%d')}.csv"
                    save_to_csv(units, output_file)
            
            finally:
                browser.close()
    
    # 全区または特定の区を処理
    elif args.all_wards or args.ward:
        if args.ward:
            # カンマ区切りで指定された区を処理
            wards_to_process = [ward.strip() for ward in args.ward.split(',')]
            print(f"指定された{len(wards_to_process)}区のトランクルーム情報をスクレイピングします...")
        else:
            # 全23区を処理
            wards_to_process = None
            print(f"東京23区全てのトランクルーム情報をスクレイピングします...")
        
        all_units, ward_results = process_all_tokyo_wards(
            wards=wards_to_process,
            limit_per_ward=args.limit,
            verbose=args.verbose,
            save_to_db=args.db,
            headless=headless
        )
        
        # 結果サマリーを表示
        print("\n=== スクレイピング結果サマリー ===")
        total_success = sum(w["success"] for w in ward_results.values())
        total_error = sum(w["error"] for w in ward_results.values())
        total_units = sum(w["units"] for w in ward_results.values())
        
        print(f"合計: 処理区={len(ward_results)}, 成功物件={total_success}, 失敗物件={total_error}, 合計区画数={total_units}")
        
        for ward_name, result in ward_results.items():
            print(f"  {ward_name}: 成功={result['success']}, 失敗={result['error']}, 区画数={result['units']}")
        
        # CSVに保存
        if args.csv and all_units:
            output_file = args.output or f"trunkroom_units_tokyo_{datetime.date.today().strftime('%Y%m%d')}.csv"
            save_to_csv(all_units, output_file)
    
    # 千代田区の処理（既存の処理を変更）
    else:
        print("千代田区のトランクルーム情報をスクレイピングします...")
        all_units, facility_success, facility_error = process_chiyoda_units(
            limit=args.limit,
            verbose=args.verbose,
            save_to_db=args.db,
            headless=headless
        )
        
        print(f"処理完了: 成功={facility_success}, 失敗={facility_error}, 合計区画数={len(all_units)}")
        
        # CSVに保存
        if args.csv and all_units:
            output_file = args.output or f"trunkroom_units_chiyoda_{datetime.date.today().strftime('%Y%m%d')}.csv"
            save_to_csv(all_units, output_file)
