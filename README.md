# Polymarket BTC Scalping Client

## プロジェクトの目的
このプロジェクトは、複数の取引所からビットコイン(BTC)の価格を集約して監視し、Polymarket上のBTC市場で取引（オーダーの発注）を行うためのWebクライアントアプリケーションです。

## 主な機能
*   **BTC価格のリアルタイム集約**: Binance, Coinbase, Kraken, OKXなどの複数取引所からWebSocketを介してBTCの価格データをリアルタイムに取得・集約し、現在の中央値（疑似レート）を算出します。
*   **Polymarket市場データの取得**: PolymarketのBTC関連市場（BTC Up/Down 5mなど）の情報をREST APIで取得し、現在のアクティブな市場情報を一覧表示します。
*   **リアルタイムな市場データの更新**: PolymarketのWebSocketに接続し、価格変動やオーダーブックの更新をリアルタイムで監視・反映します。
*   **オーダー発注機能**: クライアントUIからPolymarket上の指定したトークンに対して、注文（BUY/SELL）を発注することができます。
*   **WebベースのUI**: FastAPIを用いたバックエンドと、HTML/JS/CSSによるフロントエンドを提供し、ブラウザ上から視覚的に市場データを確認しつつ操作を行うことができます。
