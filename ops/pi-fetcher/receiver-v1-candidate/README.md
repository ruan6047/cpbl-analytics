# 固定接口：cpbl393-sftp-drop/v1-candidate.1

本地候選已固定，供WP3以receiver-contract.json實作同合同sender；不等真機帳號/key/DB解禁才寫本機碼。沒有新Web API、forced-command程式、通用controller或ready狀態機；接收端唯一實作是既有OpenSSH internal-sftp的設定模板。**不是server已可連或sender已完成**。

## sender直接使用的三組資料

1. endpoint=cpbl393-receiver@45.76.100.29:22；固定ED25519 pin見contract。身分/數字UID999/GID3993與Pi專用key引用均提議待核、尚未建立，不是root或Mac/Actions key。未生成公開key/fingerprint先保留運維引用；實際部署時再由同一新核發生成並綁定，不填假值。UID999是為原raw0700/0600與現有a905 UID999相容；主機是否可用不是本輪現場結論，衝突停下交原權責。
2. ForceCommand/chroot/allowlist精確語法見sshd-receiver.conf.in；唯一可寫host根/sftp內根與權限見contract及DEPLOYMENT-MANIFEST。原manifest/bundle1不變，run_id沿既有manifest_id及原ID_RE。原始manifest仍由consumer在bundle外獨立保存，不讓receiver寫/requests。不存在新ready目錄或DB自動觸發。
3. sender rc0只代表local helper precheck與整份batch成功，rc1代表任一失敗/未知；native sftp_rc保留原值，不捏造255/其他碼的統一含義。先mkdir claim→responses→index暫名→rename最後index，任何mkdir/put/rename失敗就batch中止，不忽略/遞迴/resume/retry/delete或換runID繞過。初始mkdir拒收原因不明時不假判“必為既存”；傳輸最後ack遺失可留完整或部分包，仍列unknown，不能接DB。

示例batch只有既有SFTP命令（WP3按validated index展開response數量，不能把註解當run command）：

```text
mkdir /incoming/<manifest_id>
mkdir /incoming/<manifest_id>/responses
put "<local_bundle>/responses/<request_id>.body" /incoming/<manifest_id>/responses/<request_id>.body
put "<local_bundle>/index.json" /incoming/<manifest_id>/.index.json.upload
rename /incoming/<manifest_id>/.index.json.upload /incoming/<manifest_id>/index.json
```

Pi呼叫為system sftp，-b本次batch、-P22、專用-i、IdentitiesOnly/BatchMode/StrictHostKeyChecking=yes、指定known_hosts，ConnectTimeout10/ServerAliveInterval10/ServerAliveCountMax3；不PTY或agent forwarding。既有批次首錯中止可防循正常接口的sender誤覆寫同run；不是伺服器write-once保證。

## 審核前必須明確保留的唯一傳輸風險

**標準SFTP仍允許同一被授權帳號以open/write或posix-rename改寫自己的既存檔案。** server不會根據run_id强制immutable，也不跑verify_bundle。候選以可信producer的排他mkdir、batch首錯停與同run禁止傳輸/消費並行滿足“不誤覆寫”；chroot/權限限制帳號越界，不能拿client約束當惡意帳號安全邊界。兩端本機候選與同版獨立審核可以先完成；真機部署前仍需原權責接受這個精確模型。若要求不遵守client時也server強制拒收，這個候選就不滿足，不能暗加wrapper或當接口已核。

既有verify_bundle(require_complete=True)/read_response會檢manifest SHA、complete/close_returned/stopped、entries順序/範圍/size/hash與symlink；原replay入口先bundle gate後DB import/write，且仍檢year/kind資料scope。傳輸完成只是讓consumer有候選包，不等於驗證通過、writer已跑或資料較正式站新。後續原manifest來源、輸入停止改動、差異/覆寫基準/可回復備份/單writer及正式首寫授權仍照WP4，不在本輪改或查。

## 一份後續整合部署租用所需項目

DEPLOYMENT-MANIFEST.json已列兩端精確候選檔/目的地/owner-mode、新帳號/key/public綁定、root-owned chroot父權限、sshd Include/Match及版本相容、保留管理通道與原owner安全載入/恢復、一次真直送及退出/部分保留收據。這些全未核發。真key/系統布局在同份核發前置產生/確認，不先碰Pi/VPS，不把部署未知變成sender候選的假依賴，也不借既有Mac管理SFTP當常態合同。

本輪只有模板/JSON文稿，沒有執行sshd或sftp、沒有生成key/建立root或帳號、沒有新測試/工具，未改任何repo/舊產物/排程/DB/備份。官方語法依先前已讀OpenSSH手冊：https://man.openbsd.org/sshd_config 、https://man.openbsd.org/sftp-server 、https://man.openbsd.org/sftp.1 。實際平台能力仍未驗。
