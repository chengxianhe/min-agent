# 使用方式

启动本机 Web Agent：

```bash
PYTHONPATH=src python3 -m min_agent.web_app \
  --workspace examples/workspace \
  --runs-dir runs \
  --port 8765
```

打开终端输出的网址后，可以选择首屏预置任务快速体验：

1. 总结工作区资料，观察只读循环。
2. 生成 `summary.md`，观察写文件权限申请。
3. 获取当前时间并生成总结，观察任务分解、命令权限和跨任务产物。

Fake 模式离线决策；DeepSeek 模式让真实模型参与判断，但工具仍在本地注册表中校验和执行。
