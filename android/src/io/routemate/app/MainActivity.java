package io.routemate.app;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.util.Locale;

/**
 * ROUTE MATE 차량용 앱.
 *
 * 화면과 판단 로직은 ROUTE MATE 서비스(FastAPI)가 제공하고, 이 앱은 차량 중앙 화면에 그것을 띄운다.
 * 음성 안내는 차량(Android)의 TTS 엔진으로 읽는다 — 웹 화면의 voice.js 가 window.RouteMateNative.speak() 를 호출한다.
 * Pleos SDK(위치·차량 상태·내비게이션·TTS) 연동은 이 클래스에 브리지 메서드를 추가하는 방식으로 확장한다.
 */
public class MainActivity extends Activity {
    static final String APP_URL = "https://route-mate-eboj.onrender.com/?native=android";

    private WebView web;
    private TextView loading;
    private TextToSpeech tts;
    private boolean ttsReady = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0c1220"));

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        web.setBackgroundColor(Color.parseColor("#0c1220"));
        web.addJavascriptInterface(new NativeBridge(), "RouteMateNative");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                loading.setVisibility(View.GONE);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    loading.setVisibility(View.VISIBLE);
                    loading.setText("연결이 원활하지 않아요.\n네트워크를 확인한 뒤 다시 열어 주세요.");
                }
            }
        });

        loading = new TextView(this);
        loading.setText("ROUTE MATE\n\n불러오는 중이에요…\n(무료 서버라 첫 실행은 최대 1분 걸릴 수 있어요)");
        loading.setTextColor(Color.parseColor("#eef2f8"));
        loading.setTextSize(24);
        loading.setGravity(Gravity.CENTER);
        loading.setBackgroundColor(Color.parseColor("#0c1220"));

        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(loading, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        tts = new TextToSpeech(this, new TextToSpeech.OnInitListener() {
            @Override
            public void onInit(int status) {
                if (status == TextToSpeech.SUCCESS) {
                    int r = tts.setLanguage(Locale.KOREAN);
                    ttsReady = r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED;
                }
            }
        });

        web.loadUrl(APP_URL);
    }

    /** 웹 화면에서 호출하는 차량 기능 브리지. */
    class NativeBridge {
        @JavascriptInterface
        public boolean available() {
            return ttsReady;
        }

        @JavascriptInterface
        public void speak(String text, float rate) {
            if (!ttsReady || text == null) return;
            tts.setSpeechRate(rate <= 0 ? 1.0f : rate);
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "routemate");
        }

        @JavascriptInterface
        public void stop() {
            if (tts != null) tts.stop();
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (tts != null) tts.shutdown();
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
