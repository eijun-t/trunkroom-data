import os
from dotenv import load_dotenv
import streamlit as st
from supabase import create_client, Client
import datetime

# .envファイルを読み込む
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def login(email: str, password: str):
    supabase = get_supabase_client()
    result = supabase.auth.sign_in_with_password({"email": email, "password": password})
    return result

def signup(email: str, password: str):
    supabase = get_supabase_client()
    result = supabase.auth.sign_up({"email": email, "password": password})

    if result.user:  # サインアップ成功時だけDBにも登録する
        user_id = result.user.id
        insert_user_to_db(user_id, email)

    return result

def insert_user_to_db(user_id: str, email: str):
    supabase = get_supabase_client()
    data = {
        "id": user_id,
        "email": email,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    # データはリストで渡す
    result = supabase.table("users").insert([data]).execute()
    return result

# --- ここから下がテスト用コード ---
if __name__ == "__main__":
    import getpass

    print("Supabase認証テスト")
    mode = input("1: ログイン, 2: 新規登録 どちらをテストしますか？（1/2）: ")

    email = input("メールアドレス: ")
    password = getpass.getpass("パスワード（表示されません）: ")

    if mode == "1":
        result = login(email, password)
        if result.user:
            insert_user_to_db(result.user.id, result.user.email)
            print("ログイン成功！ユーザー情報もDBに追加されました。")
        else:
            print("ログイン失敗:", result)
    elif mode == "2":
        result = signup(email, password)
        if result.user:
            print("新規登録成功！ユーザー情報もDBに追加されました。")
        else:
            print("新規登録失敗:", result)
    else:
        print("1か2を選んでください。")
