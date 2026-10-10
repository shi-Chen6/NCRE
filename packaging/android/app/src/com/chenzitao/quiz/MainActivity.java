package com.chenzitao.quiz;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.KeyEvent;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.OutputStream;

/**
 * 选择题刷题 —— 全屏 WebView 容器。
 *
 * 页面（assets/quiz.html）是纯前端单文件，这里只负责：
 *   1. 开 DOM Storage，让答题进度存在本机（卸载才会清）
 *   2. 接管返回键 → 页面后退，而不是直接退出
 *   3. 暴露 AndroidSave.png(dataUrl, name) 给页面，把成绩单存进相册
 *
 * 页面脚本会先判断 window.AndroidSave 是否存在：
 * 存在就走原生保存，不存在就沿用浏览器那套 <a download>。
 */
public class MainActivity extends Activity {

    private static final int REQ_WRITE = 1001;

    private WebView web;
    private String pendingDataUrl;
    private String pendingName;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // localStorage：答题进度靠它持久化
        s.setAllowFileAccess(true);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setSupportZoom(false);
        s.setTextZoom(100);
        s.setLoadWithOverviewMode(false);
        s.setUseWideViewPort(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        web.setWebViewClient(new WebViewClient());
        web.setBackgroundColor(0xFFF4F6FA);
        web.addJavascriptInterface(new Bridge(), "AndroidSave");

        web.loadUrl("file:///android_asset/quiz.html");
        setContentView(web);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web != null && web.canGoBack()) {
            web.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    /** 暴露给页面 JS 的桥：AndroidSave.png("data:image/png;base64,...", "成绩单.png") */
    private class Bridge {
        @JavascriptInterface
        public void png(final String dataUrl, final String fileName) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    savePng(dataUrl, fileName);
                }
            });
        }
    }

    private void savePng(String dataUrl, String fileName) {
        if (dataUrl == null || dataUrl.indexOf(',') < 0) {
            toast("导出失败：没有拿到图片数据");
            return;
        }
        String name = (fileName == null || fileName.length() == 0) ? "成绩单" : fileName;
        if (!name.toLowerCase().endsWith(".png")) {
            name = name + ".png";
        }
        if (Build.VERSION.SDK_INT < 29
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED) {
            pendingDataUrl = dataUrl;
            pendingName = name;
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_WRITE);
            return;
        }
        writeToGallery(dataUrl, name);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode != REQ_WRITE) {
            return;
        }
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED
                && pendingDataUrl != null) {
            writeToGallery(pendingDataUrl, pendingName);
        } else {
            toast("没有存储权限，无法保存到相册");
        }
        pendingDataUrl = null;
        pendingName = null;
    }

    private void writeToGallery(String dataUrl, String name) {
        try {
            byte[] bytes = Base64.decode(dataUrl.substring(dataUrl.indexOf(',') + 1), Base64.DEFAULT);

            ContentValues cv = new ContentValues();
            cv.put(MediaStore.Images.Media.DISPLAY_NAME, name);
            cv.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
            if (Build.VERSION.SDK_INT >= 29) {
                cv.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/" + getString(R.string.app_name));
                cv.put(MediaStore.Images.Media.IS_PENDING, 1);
            }
            Uri uri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cv);
            if (uri == null) {
                toast("保存失败：相册拒绝写入");
                return;
            }
            OutputStream os = getContentResolver().openOutputStream(uri);
            if (os == null) {
                toast("保存失败：无法打开输出流");
                return;
            }
            os.write(bytes);
            os.flush();
            os.close();
            if (Build.VERSION.SDK_INT >= 29) {
                cv.clear();
                cv.put(MediaStore.Images.Media.IS_PENDING, 0);
                getContentResolver().update(uri, cv, null, null);
            }
            toast("已保存到相册：Pictures/" + getString(R.string.app_name));
        } catch (Exception e) {
            toast("保存失败：" + e.getMessage());
        }
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
    }
}
