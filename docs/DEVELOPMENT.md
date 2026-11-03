# 开发说明

## 环境与运行

使用 Python 3.12，在项目虚拟环境中安装 `requirements.txt` 和 `requirements-dev.txt`。运行 `app.py` 后，工作台位于 http://127.0.0.1:5000 。各平台安装命令见 [README](../README.md)。

## 项目结构

- `app.py`：HTTP 入口和上传校验。
- `voxfigure/`：几何、皮肤映射、颜色量化和分件导出。
- `assets/steve/`、`assets/alex/`：Steve / Alex STEP 模型。
- `templates/`、`static/`：工作台界面与本地前端依赖。
- `tests/`：接口、皮肤、模型及导出测试。

工作台使用 `/`、`/api/options`、`/api/generate`、`/api/export` 和静态资源路由。

## 测试

普通测试默认排除 `cad` 标记。在 Windows PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

包含真实 STEP 生成与 3MF 导出的全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -o addopts=
```

macOS / Linux 将解释器路径替换为 `.venv/bin/python`。CAD 测试依赖 CadQuery / OCP，首次运行耗时较长。

浏览器测试使用 `tests/browser.cjs`，需要 Node.js、Playwright 及其浏览器。通过 `VF_URL` 指向已启动的本地服务；`VF_UI_ONLY=1` 只检查界面和接口，不调用 CAD 生成。修改预览或导出时，应检查 Steve / Alex、皮肤透明层、语言、主题和窄屏布局。

## 缓存与临时文件

几何缓存默认位于 `.cache`，可通过 `VOXFIGURE_CACHE` 修改。删除缓存会让下次生成重新处理 STEP，不改变源模型。Compose 将缓存保存在命名卷中。

上传皮肤与导出临时文件在请求结束后清理。Three.js 随项目提供，不从外部 CDN 加载。

## 提交变更

提交前运行与改动相关的测试，说明复现步骤、修改内容和验证结果。模型改动请同时检查预览与 3MF 导出，并更新必要的署名和许可说明。
