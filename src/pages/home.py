import os
import sys

# プロジェクトのルートパスを動的に計算
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, root_path)

import streamlit as st
from src.auth.auth import login, signup, get_supabase_client

def main():
    st.title("認証ページ")
    
    # セッション状態の初期化
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    
    # すでに認証済みの場合
    if st.session_state.authenticated:
        st.success(f"ログイン中: {st.session_state.user['email']}")
        if st.button("ログアウト"):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.rerun()
        return
    
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
