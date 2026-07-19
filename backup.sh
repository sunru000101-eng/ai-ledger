#!/bin/bash
# 账本备份管理：
#   bash backup.sh          备份当前账本（自动清理14天前旧备份）
#   bash backup.sh list     列出所有历史备份
#   bash backup.sh restore  交互式选择历史备份恢复

set -e
cd "$(dirname "$0")"

DB_PATH="data/ledger.db"
BACKUP_DIR="data/backups"
KEEP_DAYS=14

usage() {
  echo "用法："
  echo "  bash backup.sh          备份当前账本"
  echo "  bash backup.sh list     列出所有历史备份"
  echo "  bash backup.sh restore  从历史备份恢复账本"
  exit 1
}

do_backup() {
  if [ ! -f "$DB_PATH" ]; then
    echo "⚠️  账本文件还不存在（$DB_PATH），跳过备份"
    return 0
  fi
  mkdir -p "$BACKUP_DIR"
  local ts target size count
  ts="$(date +'%Y-%m-%d-%H%M')"
  target="$BACKUP_DIR/ledger-$ts.db"
  # sqlite3 .backup 命令即使服务在跑也能安全备份；失败退回到 cp
  sqlite3 "$DB_PATH" ".backup '$target'" 2>/dev/null || cp "$DB_PATH" "$target"
  size="$(du -h "$target" | cut -f1 | tr -d ' ')"
  echo "✅ 已备份：$target（$size）"
  find "$BACKUP_DIR" -name "ledger-*.db" -type f -mtime +$KEEP_DAYS -delete 2>/dev/null || true
  count="$(ls -1 "$BACKUP_DIR"/ledger-*.db 2>/dev/null | wc -l | tr -d ' ')"
  echo "   现有历史备份 $count 份（自动保留 $KEEP_DAYS 天内）"
}

do_list() {
  if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -1 "$BACKUP_DIR"/ledger-*.db 2>/dev/null)" ]; then
    echo "尚无历史备份"
    return 0
  fi
  echo "历史备份（新 → 旧）："
  ls -1t "$BACKUP_DIR"/ledger-*.db | while read -r f; do
    printf "  %s  %s\n" "$(du -h "$f" | cut -f1)" "$f"
  done
}

do_restore() {
  if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -1 "$BACKUP_DIR"/ledger-*.db 2>/dev/null)" ]; then
    echo "没有可恢复的历史备份"
    exit 1
  fi
  echo "可选择的历史备份（新 → 旧）："
  local sorted=()
  local i=1
  while IFS= read -r f; do
    sorted+=("$f")
    echo "  $i) $f"
    i=$((i+1))
    [ $i -gt 20 ] && break
  done < <(ls -1t "$BACKUP_DIR"/ledger-*.db)
  echo ""
  read -r -p "输入序号选择要恢复的备份（直接回车=取消）: " choice
  if [ -z "$choice" ]; then
    echo "已取消"
    exit 0
  fi
  local pick="${sorted[$((choice-1))]}"
  if [ -z "$pick" ] || [ ! -f "$pick" ]; then
    echo "❌ 序号无效"
    exit 1
  fi
  if [ -f "$DB_PATH" ]; then
    local safety
    safety="$BACKUP_DIR/ledger-before-restore-$(date +'%Y-%m-%d-%H%M').db"
    cp "$DB_PATH" "$safety"
    echo "🛡️  恢复前先把当前账本安全存了一份：$safety"
  fi
  cp "$pick" "$DB_PATH"
  echo "✅ 已恢复：$pick"
  echo "   记得重启服务让新数据生效（关掉终端窗口，再双击「启动AI记账」）"
}

case "${1:-backup}" in
  backup|"") do_backup ;;
  list)     do_list ;;
  restore)  do_restore ;;
  *) usage ;;
esac
