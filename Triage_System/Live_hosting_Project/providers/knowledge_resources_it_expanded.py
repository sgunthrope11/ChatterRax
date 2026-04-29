IT_KNOWLEDGE_RESOURCES = (
    # ---------------------------------------------------------- APP-SCOPED SSO
    {
        "id": "outlook_sso_wam_token_loop",
        "service": "outlook",
        "intent": "sign_in",
        "title": "Outlook single sign-on token loop or repeated credential prompt",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("outlook", "mail", "mailbox", "exchange"),
            ("sso", "single sign on", "single sign-on", "seamless sign in", "wam", "credential prompt", "keeps asking"),
        ),
        "keywords": (
            "outlook", "mail", "exchange", "sso", "single sign on", "single sign-on",
            "seamless sign in", "wam", "web account manager", "credential prompt",
            "keeps asking", "sign in loop", "modern authentication", "cached token",
            "work or school account", "aadsts", "office token", "windows credentials",
        ),
        "steps": (
            "Confirm Outlook on the web works with the same account so the mailbox and license are valid.",
            "Close Outlook, reopen it, and sign in when prompted so the app can request a fresh modern-auth token.",
            "In Windows Settings > Accounts > Access work or school, confirm the expected work account is connected.",
            "If only desktop Outlook loops, remove stale Outlook or Office entries from Credential Manager and restart Outlook.",
        ),
        "advanced_steps": (
            "Check whether the device is Hybrid Entra joined or Entra joined as expected; a broken device registration can cause WAM token loops.",
            "If the error includes AADSTS or Conditional Access wording, capture the correlation ID, timestamp, and sign-in app for admin review.",
        ),
    },
    {
        "id": "teams_sso_desktop_token_cache",
        "service": "teams",
        "intent": "sign_in",
        "title": "Teams desktop single sign-on or Web Account Manager cache issue",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("teams", "meeting", "chat", "channel"),
            ("sso", "single sign on", "single sign-on", "wam", "token", "sign in loop", "keeps signing"),
        ),
        "keywords": (
            "teams", "sso", "single sign on", "single sign-on", "wam", "token",
            "sign in loop", "keeps signing", "keeps asking", "blank login",
            "auth loop", "desktop app", "web works", "cached account",
            "work or school account", "conditional access", "aadsts",
        ),
        "steps": (
            "Try Teams on the web first; if web works, keep the issue on the Teams desktop sign-in path.",
            "Fully quit Teams from the system tray, reopen it, and choose the correct work account.",
            "In Windows Settings > Accounts > Access work or school, disconnect only stale work accounts you no longer use.",
            "If Teams desktop still loops, clear the Teams cache and sign in again.",
        ),
        "advanced_steps": (
            "Check whether Conditional Access requires a compliant device; Teams desktop may fail while browser sign-in succeeds differently.",
            "For repeated AADSTS errors, collect the timestamp and correlation ID before changing account policies.",
        ),
    },
    {
        "id": "onedrive_sso_tenant_mismatch",
        "service": "onedrive",
        "intent": "sign_in",
        "title": "OneDrive single sign-on opens the wrong tenant or account",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("onedrive", "one drive", "sync client", "cloud files"),
            ("sso", "single sign on", "single sign-on", "wrong tenant", "wrong account", "account mismatch"),
        ),
        "keywords": (
            "onedrive", "sso", "single sign on", "single sign-on", "wrong tenant",
            "wrong account", "account mismatch", "business account", "personal account",
            "work account", "school account", "sync client", "unlink this pc",
            "tenant", "cached account", "work or school account",
        ),
        "steps": (
            "Open the OneDrive cloud icon, go to Settings > Account, and verify the signed-in email and tenant.",
            "If the wrong account is connected, use Unlink this PC and sign in with the correct work or school account.",
            "Confirm the expected OneDrive files are visible on the web before choosing a local sync folder.",
            "Let OneDrive finish indexing before deciding files are missing.",
        ),
        "advanced_steps": (
            "Check whether Windows has multiple Access work or school accounts that could be feeding the wrong SSO token.",
            "If tenant discovery keeps picking the wrong organization, collect the UPN being used and the tenant shown in the OneDrive web URL.",
        ),
    },
    {
        "id": "sharepoint_sso_conditional_access_denied",
        "service": "sharepoint",
        "intent": "permissions",
        "title": "SharePoint SSO succeeds but Conditional Access or permissions block the site",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("sharepoint", "site", "document library", "library link"),
            ("sso", "single sign on", "single sign-on", "conditional access", "access denied", "permission"),
        ),
        "keywords": (
            "sharepoint", "site", "document library", "sso", "single sign on",
            "single sign-on", "conditional access", "access denied", "permission",
            "not authorized", "blocked by policy", "compliant device", "managed device",
            "private window", "wrong account", "tenant",
        ),
        "steps": (
            "Open the SharePoint site in a private browser window and sign in with the expected work account.",
            "If private browsing works, clear stale browser sessions for Microsoft 365 and retry the normal browser.",
            "If it still says access denied, open the site root rather than an old shared link to separate link age from permission.",
            "Ask the site owner to confirm your permission on the exact library or file, not just the parent site.",
        ),
        "advanced_steps": (
            "If the page says blocked by policy or compliant device required, the next check is Conditional Access and device compliance.",
            "For admin escalation, capture the URL, timestamp, signed-in UPN, and whether the browser shows the expected tenant.",
        ),
    },
    {
        "id": "office_apps_sso_activation_license",
        "service": "microsoft 365",
        "intent": "sign_in",
        "title": "Office apps SSO signs in but activation or licensing does not follow",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("office", "microsoft 365", "word", "excel", "powerpoint"),
            ("sso", "single sign on", "single sign-on", "activation", "license", "unlicensed"),
        ),
        "keywords": (
            "office", "microsoft 365", "word", "excel", "powerpoint", "sso",
            "single sign on", "single sign-on", "activation", "license",
            "unlicensed", "subscription", "signed in but", "product deactivated",
            "account error", "office account", "connected services",
        ),
        "steps": (
            "Open any Office app, go to File > Account, and confirm the signed-in account is the licensed work account.",
            "Sign out of Office apps, close all Office windows, then sign back in from one Office app.",
            "Check microsoft365.com in a browser with the same account to confirm the license is assigned.",
            "If one app works and another does not, repair Microsoft 365 Apps rather than changing the account first.",
        ),
        "advanced_steps": (
            "If activation still fails, clear Office identity caches only after confirming the user has a valid license.",
            "For managed devices, compare the user's license assignment with shared computer activation or device-based licensing policy.",
        ),
    },
    {
        "id": "windows_work_school_account_sso_broken",
        "service": "windows",
        "intent": "sign_in",
        "title": "Windows work or school account is breaking Microsoft 365 SSO",
        "source": "Local Windows IT playbook",
        "required_any": (
            ("windows", "pc", "laptop", "device", "work or school account"),
            ("sso", "single sign on", "single sign-on", "work or school", "access work or school", "device registration"),
        ),
        "keywords": (
            "windows", "work or school account", "access work or school", "sso",
            "single sign on", "single sign-on", "device registration",
            "entra joined", "azure ad joined", "hybrid joined", "dsregcmd",
            "connected account", "account needs attention", "organization",
        ),
        "steps": (
            "Open Settings > Accounts > Access work or school and check whether the expected organization account is connected.",
            "If Windows says the account needs attention, select it and fix the sign-in prompt before testing Office apps again.",
            "Restart after repairing the work account so Windows Web Account Manager refreshes its tokens.",
            "Do not disconnect a managed work account unless you know the device is not controlled by that organization.",
        ),
        "advanced_steps": (
            "For IT review, run device registration checks and verify the device join state matches the organization's sign-in policy.",
            "If Conditional Access requires compliance, confirm the device is compliant before troubleshooting each app separately.",
        ),
    },
    # ------------------------------------------------------------ DEEP FIXES
    {
        "id": "outlook_ost_profile_rebuild",
        "service": "outlook",
        "intent": "sync",
        "title": "Outlook desktop cache or profile is stale while webmail is correct",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("outlook", "mail", "mailbox"),
            ("web works", "webmail works", "desktop only", "cache", "profile", "ost", "not updating"),
        ),
        "keywords": (
            "outlook", "web works", "webmail works", "desktop only", "cache",
            "profile", "ost", "mailbox not updating", "old mail", "search stale",
            "new profile", "cached exchange mode", "repair profile",
        ),
        "steps": (
            "Confirm Outlook on the web shows the correct mailbox state before changing the desktop app.",
            "Close Outlook, reopen it, and let Send/Receive finish once.",
            "Create a new Outlook profile if the same mailbox is correct on the web but stale in desktop Outlook.",
            "Keep the old profile until the new one has fully synced and the user confirms calendar and shared mailboxes are present.",
        ),
        "advanced_steps": (
            "Check add-ins and antivirus mail scanning if the profile rebuild works briefly then stalls again.",
            "If multiple users are affected, check Exchange service health before rebuilding individual profiles.",
        ),
    },
    {
        "id": "teams_meeting_policy_features_missing",
        "service": "teams",
        "intent": "permissions",
        "title": "Teams meeting feature is missing because of policy or organizer role",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("teams", "meeting", "webinar", "town hall"),
            ("missing", "disabled", "greyed out", "policy", "organizer", "presenter"),
        ),
        "keywords": (
            "teams", "meeting", "policy", "organizer", "presenter", "missing",
            "disabled", "greyed out", "recording missing", "transcription missing",
            "breakout rooms", "webinar", "town hall", "meeting options",
        ),
        "steps": (
            "Confirm whether the user is organizer, co-organizer, presenter, or attendee because Teams exposes different controls for each role.",
            "Leave and rejoin after the organizer changes meeting options so the role refreshes.",
            "Try Teams on the web to separate a policy or role problem from desktop cache.",
            "If the feature is missing for many meetings, the Teams meeting policy may need admin review.",
        ),
        "advanced_steps": (
            "Compare the user's assigned Teams meeting policy with a user who has the feature.",
            "Check whether the feature is disabled by tenant policy, meeting template, sensitivity label, or organizer setting.",
        ),
    },
    {
        "id": "onedrive_known_folder_move_blocked",
        "service": "onedrive",
        "intent": "sync",
        "title": "OneDrive backup for Desktop, Documents, or Pictures is blocked",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("onedrive", "desktop", "documents", "pictures", "backup"),
            ("backup blocked", "folder backup", "known folder", "cannot backup", "can't backup", "cant backup"),
        ),
        "keywords": (
            "onedrive", "backup", "folder backup", "known folder", "desktop",
            "documents", "pictures", "cannot backup", "can't backup", "cant backup",
            "backup blocked", "folder protection", "sync blocked", "policy",
        ),
        "steps": (
            "Open OneDrive Settings > Sync and backup and check which folder is blocked.",
            "Move unsupported files such as local database files, PST files, or very large archives out of the protected folder.",
            "Start folder backup again after clearing the listed blocker.",
            "If the setting is controlled by your organization, do not override it locally; ask IT to confirm the OneDrive policy.",
        ),
        "advanced_steps": (
            "Check for redirected folders, unsupported file types, and local policy conflicts before resetting OneDrive.",
            "If many users are affected, review Known Folder Move policy and tenant sync restrictions.",
        ),
    },
    {
        "id": "sharepoint_external_sharing_blocked",
        "service": "sharepoint",
        "intent": "permissions",
        "title": "SharePoint external sharing is blocked or guest access fails",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("sharepoint", "sharing link", "guest", "external"),
            ("blocked", "cannot share", "can't share", "cant share", "external sharing", "guest access"),
        ),
        "keywords": (
            "sharepoint", "external sharing", "guest", "guest access", "sharing link",
            "cannot share", "can't share", "cant share", "blocked", "anyone link",
            "specific people", "organization policy", "external user",
        ),
        "steps": (
            "Check whether sharing works with an internal user first; that separates file permission from external sharing policy.",
            "Use Specific people instead of Anyone link if the organization blocks anonymous links.",
            "Ask the site owner to confirm external sharing is allowed on that site.",
            "If the guest already exists, have them sign out and open the invite in a private browser session.",
        ),
        "advanced_steps": (
            "For admin review, compare tenant-level external sharing, site-level sharing, and sensitivity label restrictions.",
            "If the external user changed email aliases, remove the stale guest object before reinviting.",
        ),
    },
    {
        "id": "excel_protected_view_trust_center",
        "service": "excel",
        "intent": "permissions",
        "title": "Excel blocks a workbook in Protected View or Trust Center",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("excel", "workbook", "spreadsheet"),
            ("protected view", "trust center", "blocked", "enable editing", "macro"),
        ),
        "keywords": (
            "excel", "protected view", "trust center", "blocked", "enable editing",
            "macro", "macros disabled", "downloaded file", "internet file",
            "trusted location", "security warning", "yellow bar",
        ),
        "steps": (
            "If you trust the file source, save a copy to a trusted local folder and reopen it.",
            "Use Enable Editing only after confirming the sender and file are legitimate.",
            "If macros are required, confirm the workbook is from a trusted source before enabling content.",
            "For recurring business files, ask IT whether a Trusted Location or signed macro is appropriate.",
        ),
        "advanced_steps": (
            "Check whether Mark of the Web is present on the file properties and whether policy blocks internet macros.",
            "Do not lower global Trust Center settings as a workaround; use file-specific trust or admin policy.",
        ),
    },
    {
        "id": "word_template_normal_dotm_corrupt",
        "service": "word",
        "intent": "crash",
        "title": "Word opens slowly or crashes because the normal template or add-ins are corrupt",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("word", "document", "docx"),
            ("slow", "crash", "crashes", "not responding", "template", "add-in"),
        ),
        "keywords": (
            "word", "slow", "crash", "crashes", "not responding", "normal template",
            "normal.dotm", "template", "add-in", "addin", "safe mode",
            "opens slowly", "blank document slow",
        ),
        "steps": (
            "Start Word in safe mode by holding Ctrl while opening Word; if it behaves, an add-in or template is likely involved.",
            "Disable nonessential COM add-ins and reopen Word normally.",
            "If blank documents are also slow, rename the Normal.dotm template so Word creates a fresh one.",
            "Keep a backup of custom templates before replacing them.",
        ),
        "advanced_steps": (
            "Check startup folders for global templates that load into every Word session.",
            "If the issue follows only one document, copy content into a clean document instead of changing global Word settings.",
        ),
    },
    {
        "id": "powerpoint_corporate_template_missing_assets",
        "service": "powerpoint",
        "intent": "formatting",
        "title": "PowerPoint corporate template assets or fonts are missing",
        "source": "Local Microsoft 365 IT playbook",
        "required_any": (
            ("powerpoint", "presentation", "slide deck", "template"),
            ("template", "font", "brand", "logo", "layout", "missing"),
        ),
        "keywords": (
            "powerpoint", "template", "font", "fonts", "brand", "logo",
            "layout", "missing", "corporate template", "theme", "slide master",
            "assets", "placeholder", "wrong layout",
        ),
        "steps": (
            "Open View > Slide Master and confirm the deck is using the expected corporate template.",
            "Check whether required fonts are installed on the device.",
            "Reapply the correct layout to affected slides before manually moving objects.",
            "If the deck is shared externally, export a PDF backup or embed fonts where licensing allows.",
        ),
        "advanced_steps": (
            "Compare the template version against a known-good deck because older masters can miss current brand assets.",
            "If the template is centrally deployed, confirm the device has received the latest Office template policy.",
        ),
    },
    {
        "id": "windows_vpn_dns_split_tunnel_issue",
        "service": "windows",
        "intent": "sync",
        "title": "Windows VPN or DNS issue blocks Microsoft 365 sign-in or sync",
        "source": "Local Windows IT playbook",
        "required_any": (
            ("windows", "vpn", "dns", "network"),
            ("microsoft 365", "office", "teams", "outlook", "onedrive", "sharepoint", "sync", "sign in"),
        ),
        "keywords": (
            "windows", "vpn", "dns", "network", "microsoft 365", "office",
            "teams", "outlook", "onedrive", "sharepoint", "sync", "sign in",
            "split tunnel", "proxy", "connected no internet", "work network",
        ),
        "steps": (
            "Disconnect VPN briefly and test the same Microsoft 365 action if policy allows.",
            "If it works off VPN, reconnect and test whether only Microsoft 365 endpoints fail or all internet traffic fails.",
            "Restart the VPN client and flush DNS by restarting Windows before changing app settings.",
            "If the issue only occurs on the corporate network, keep troubleshooting at the network/VPN layer.",
        ),
        "advanced_steps": (
            "Check proxy, DNS suffix, split tunnel, and firewall rules for Microsoft 365 endpoints.",
            "Collect the affected app, network state, VPN profile, and timestamp for network team review.",
        ),
    },
)
