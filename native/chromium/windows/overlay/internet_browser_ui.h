#ifndef CHROME_BROWSER_INTERNET_BROWSER_UI_H_
#define CHROME_BROWSER_INTERNET_BROWSER_UI_H_

#include "content/public/browser/web_ui_controller.h"
#include "content/public/browser/webui_config.h"
#include "content/public/common/url_constants.h"

class InternetBrowserUI : public content::WebUIController {
 public:
  explicit InternetBrowserUI(content::WebUI* web_ui);
  ~InternetBrowserUI() override;
};

class InternetBrowserUIConfig
    : public content::DefaultWebUIConfig<InternetBrowserUI> {
 public:
  InternetBrowserUIConfig()
      : DefaultWebUIConfig(content::kChromeUIScheme, "internet-browser") {}
};

#endif
