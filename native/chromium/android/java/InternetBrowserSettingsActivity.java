package org.chromium.chrome.browser;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;

import org.chromium.base.version_info.VersionInfo;
import org.chromium.chrome.browser.content.WebContentsFactory;
import org.chromium.chrome.browser.init.ChromeBrowserInitializer;
import org.chromium.chrome.browser.profiles.ProfileManager;
import org.chromium.components.embedder_support.delegate.WebContentsDelegateAndroid;
import org.chromium.components.embedder_support.view.ContentView;
import org.chromium.components.thinwebview.ThinWebView;
import org.chromium.components.thinwebview.ThinWebViewAttachParams;
import org.chromium.components.thinwebview.ThinWebViewConstraints;
import org.chromium.components.thinwebview.ThinWebViewFactory;
import org.chromium.content_public.browser.LoadUrlParams;
import org.chromium.content_public.browser.Visibility;
import org.chromium.content_public.browser.WebContents;
import org.chromium.content_public.common.ResourceRequestBody;
import org.chromium.ui.base.ActivityWindowAndroid;
import org.chromium.ui.base.IntentRequestTracker;
import org.chromium.ui.base.ViewAndroidDelegate;
import org.chromium.url.GURL;

/** Product settings surface. Its WebContents never enters a browser TabModel. */
public class InternetBrowserSettingsActivity extends ChromeBaseAppCompatActivity {
    private WebContents mContents;
    private ThinWebView mView;
    private ActivityWindowAndroid mWindow;
    private final WebContentsDelegateAndroid mDelegate = new WebContentsDelegateAndroid() {
        @Override
        public void closeContents() { finish(); }

        @Override
        public void openNewTab(GURL url, String headers, ResourceRequestBody body,
                int disposition, boolean rendererInitiated) {
            // Explicit links leave settings through the browser, without giving
            // remote content access to the settings WebUI's native handlers.
            if (url.getScheme().equals("https") || url.getScheme().equals("chrome")) {
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url.getSpec()));
                intent.setPackage(getPackageName());
                try { startActivity(intent); }
                catch (android.content.ActivityNotFoundException ignored) { }
            }
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        ChromeBrowserInitializer.getInstance().handleSynchronousStartup();
        super.onCreate(state);
        mWindow = new ActivityWindowAndroid(this, true,
                IntentRequestTracker.createFromActivity(this), null, false);
        mContents = WebContentsFactory.createWebContents(
                ProfileManager.getLastUsedRegularProfile(), false, false);
        ContentView content = ContentView.createContentView(this, mContents);
        mContents.setDelegates(VersionInfo.getProductVersion(),
                ViewAndroidDelegate.createBasicDelegate(content), content, mWindow,
                WebContents.createDefaultInternalsHolder());
        mView = ThinWebViewFactory.create(this, new ThinWebViewConstraints(), mWindow);
        mView.attachWebContents(mContents, content, new ThinWebViewAttachParams.Builder()
                .setWebContentsDelegate(mDelegate).build());
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setFitsSystemWindows(true);
        Button close = new Button(this);
        close.setText("‹  브라우저로 돌아가기");
        close.setOnClickListener(view -> finish());
        layout.addView(close, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        layout.addView(mView.getView(), new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(layout);
        String section = getIntent().getStringExtra("section");
        if (!"video".equals(section) && !"library".equals(section)
                && !"updates".equals(section)) section = "general";
        Uri.Builder address = Uri.parse("chrome://internet-browser/").buildUpon();
        for (String name : new String[] {"source", "media"}) {
            String value = getIntent().getStringExtra(name);
            if (value != null && value.length() <= 16384) address.appendQueryParameter(name, value);
        }
        address.fragment(section);
        mContents.getNavigationController().loadUrl(new LoadUrlParams(address.build().toString()));
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (mContents != null) mContents.updateWebContentsVisibility(Visibility.VISIBLE);
    }

    @Override
    protected void onStop() {
        if (mContents != null) mContents.updateWebContentsVisibility(Visibility.HIDDEN);
        super.onStop();
    }

    @Override
    public void onBackPressed() {
        if (mContents != null && mContents.getNavigationController().canGoBack())
            mContents.getNavigationController().goBack();
        else finish();
    }

    @Override
    protected void onDestroy() {
        if (mView != null) mView.destroy();
        if (mContents != null) mContents.destroy();
        if (mWindow != null) mWindow.destroy();
        super.onDestroy();
    }
}
