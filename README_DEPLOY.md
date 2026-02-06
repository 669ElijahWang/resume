# 部署指南 (Deployment Guide)

本指南将帮助你将项目部署到 Linux 服务器上。推荐使用 Docker 进行部署，这样可以保证环境的一致性并简化管理。

## 前置要求

确保你的服务器上安装了：
1. **Docker**: [安装文档](https://docs.docker.com/engine/install/)
2. **Docker Compose**: [安装文档](https://docs.docker.com/compose/install/)

## 部署步骤

### 1. 上传文件

将整个项目文件夹上传到服务器的某个目录（例如 `/opt/resume-screener`）。
你可以使用 SCP、SFTP 或 Git。

如果项目在 Git 仓库中：
```bash
git clone <你的仓库地址> /opt/resume-screener
cd /opt/resume-screener
```

### 2. 配置环境变量

确保根目录下有一个 `.env` 文件，并且填好了必要的配置（如 API Key）。
你可以复制示例文件（如果有）或直接创建：

```bash
cp .env.example .env  # 如果有 example
nano .env             # 编辑填入真实的 keys
```

**注意**: `.env` 文件中的敏感信息（如 API Key）不要提交到公开的代码仓库。

### 3. 构建并运行

在项目根目录下运行：

```bash
docker-compose up -d --build
```

- `-d`: 后台运行
- `--build`: 强制重新构建镜像（首次或代码更新后使用）

### 4. 验证部署

查看容器状态：
```bash
docker-compose ps
```

查看日志（如果启动失败）：
```bash
docker-compose logs -f
```

如果一切正常，可以通过 `http://<服务器IP>:9999` 访问应用。

### 5. 后续维护

**代码更新后**：
1. 拉取新代码 (`git pull`)
2. 重启容器：
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

**数据备份**：
所有数据都保存在 `data/` 目录下（包括 SQLite 数据库和上传的文件）。请定期备份该目录。

## 替代方案：手动运行 (不推荐)

如果不使用 Docker，你需要：
1. 安装 Python 3.9+。
2. 安装依赖：`pip install -r backend/requirements.txt`。
3. 后台运行：
   ```bash
   nohup uvicorn backend.main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &
   ```
