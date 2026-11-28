# 集群审计事件封存与留置庭

本地云原生审计素材源：`capture` 接收合成 API 审计事件、追踪序列缺口与源冲突；`seal` 为对象形成不可改写的版本化证据链；`hold` 裁定保留期限、调查留置、披露和清理。Python 3.11+ 标准库、SQLite，不连接真实集群或日志平台，不存真实个人数据。

```sh
python -m auditcourt demo --db demo.sqlite
python -m auditcourt replay --db demo.sqlite
python -m unittest discover -s tests -v
```

每个入口均有 `fixtures/<入口>_normal.json` 与 `_failure.json`；`demo` 按业务顺序执行。所有写操作使用 IMMEDIATE 事务，事件 ID 按原文幂等，冲突拒绝。重放从空库逐条执行事件并比较所有业务表。封存只含封存时已收到的事件，缺口填补与冲突仲裁也按实际收到时间计算；补录产生新版本，旧披露仍固定原封存版。冲突的新摘要尚无可信原事件时不能被仲裁为已采纳。时间值是合成逻辑时刻，外部可信时间源与法律权限认证不在项目范围内。

### Local custody and collector coverage

Run `python -m auditcourt custody --db audit.sqlite --fixture fixtures/custody_coverage.json` to replay collection, testimony, sealing, and vault setup. `coverage attest` proves an enumerated window was received without known disputes. The `custody` entry opens vaults, deposits a sealed chain using its digest, lists stored copies, and releases copies subject to an active hold.

### Withdrawal tickets under watch duties

A legal hold binds an actual sealed chain version, and each version keeps its own members and digest, so the hold no longer blocks every copy outright. `custody` now lands three business records:

- `watch` registers a duty on one chain version: `forensic` is the dual-failure-domain continuous-readback contract; `cold` is custodian-lead approved cold custody (`approver` required). Each carries its own responsibility window.
- `read_test` records a successful readback of one stored copy; its time cannot predate the deposit receipt.
- `withdraw` opens a withdrawal ticket for one named copy and `withdraw_complete` removes it and returns the vault slot.

Every chain version under the same held object must satisfy its own custody duty: a child/older version, a copy of another object, or a same-vault slot is not an independent backup. A valid independent backup is a stored, read-tested copy of the same chain in another vault whose watch duty covers the whole withdrawal window. Under a forensic watch, surviving read-tested copies must span two failure domains before the ticket issues — without a pre-confirmed relay the north copy stays at the window start and no withdrawal receipt is emitted. The cold contract may close online readback once the retained cold copy covers the full window. Read-tested backups are claimed on the open ticket (`copy_claim_locked` blocks ordinary release) until completion. Pending and late-arriving tickets never offset current vault capacity.

The two synthetic records for case O replay independently from an empty database:

```sh
python -m auditcourt custody --db forensic.sqlite --fixture fixtures/withdraw_forensic.json
python -m auditcourt custody --db cold.sqlite --fixture fixtures/withdraw_cold.json
python -m auditcourt replay --db forensic.sqlite
python -m auditcourt replay --db cold.sqlite
```
