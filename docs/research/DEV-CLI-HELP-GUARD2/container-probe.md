# DEV-CLI-HELP-GUARD2 — cpbl-train / cpbl-train-pitching 容器內探針取證

> **本檔由指令產生，勿手改。**重新產生：
> `bash docs/research/DEV-CLI-HELP-GUARD2/container_probe.sh > docs/research/DEV-CLI-HELP-GUARD2/container-probe.md`

掃描對象：`7ecf5efdc00cde96d33f06ad6faaa2c03b95d49f`

取證方式與判定碼定義見 `docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py` docstring——同一支工具、
同一份封鎖清單，只是換到容器內執行。`seal_gap: []` 代表該次探針的封鎖面完整。

```
$ docker compose version: 5.1.2
$ python: Python 3.12.13 (main, Aug  5 2026, 01:17:28) [GCC 12.2.0]
$ libgomp: lightgbm 4.7.0 import OK
```

## `cpbl.models.train:main`

```json
{"seal_gap": [], "help": ["SAFE", "exit=0｜usage: cpbl-train [-h]"], "dash_h": ["SAFE", "exit=0｜usage: cpbl-train [-h]"], "bad_flag": ["EXIT_NONZERO", "exit=2｜usage: cpbl-train [-h]"], "bad_positional": ["EXIT_NONZERO", "exit=2｜usage: cpbl-train [-h]"]}
```

## `cpbl.models.train_pitching:main`

```json
{"seal_gap": [], "help": ["SAFE", "exit=0｜usage: cpbl-train-pitching [-h]"], "dash_h": ["SAFE", "exit=0｜usage: cpbl-train-pitching [-h]"], "bad_flag": ["EXIT_NONZERO", "exit=2｜usage: cpbl-train-pitching [-h]"], "bad_positional": ["EXIT_NONZERO", "exit=2｜usage: cpbl-train-pitching [-h]"]}
```

