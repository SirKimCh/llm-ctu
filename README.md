# llm-ctu — Chatbot tư vấn tuyển sinh/đào tạo

Đồ án môn **Xử lý ngôn ngữ tự nhiên — Đề tài 4: Trợ lý ảo Chatbot tư vấn tuyển sinh/đào tạo**.

Luồng xử lý: tri thức (import Excel hoặc cào bằng Brightdata) → **MySQL** → người dùng chat trên web →
**PhoBERT fine-tune** nhận diện ý định + thực thể → **LangGraph** quản lý hội thoại (trạng thái lưu MySQL) →
truy xuất dữ kiện (FULLTEXT ngram) → **LLM qua Ollama** chỉ diễn đạt lại dữ kiện ở bước cuối.

Stack: Python 3.12 · uv · FastAPI + Jinja2 · MySQL 8.0 · SQLAlchemy 2 · LangGraph · PyTorch + Transformers · pyvi · Ollama (`qwen2.5:7b`).

---

## 1. Repo KHÔNG chứa những gì (đọc trước khi clone)

Theo `.gitignore`, các mục sau **không có** trong repo. Máy mới phải tự bổ sung:

| Thiếu | Hậu quả | Cách bổ sung |
|---|---|---|
| `.env` | App không chạy | `Copy-Item .env.example .env` rồi sửa giá trị (mục 4) |
| `artifacts/nlu/model.safetensors` (~540 MB, trọng số PhoBERT đã fine-tune) | Bước kiểm tra NLU báo lỗi, app không khởi động | **Cách A:** chép file từ máy đã huấn luyện vào `artifacts/nlu/`. **Cách B:** tự huấn luyện lại bằng notebook (mục 6) |
| `.venv/` | — | `uv` tự tạo khi chạy lệnh đầu tiên |
| `docs/`, `tests/`, `docsAI/`, `FinalPaper/`, `CLAUDE.md` | Không ảnh hưởng việc chạy app; không chạy được `pytest` | Tài liệu nội bộ, không phát hành. Một số thông báo lỗi nhắc tới `docs/…` — xem mục 8 của README này thay thế |

Các file còn lại của `artifacts/nlu/` (tokenizer, `config.json`, `labels.json`, `metrics.json`) **có** trong repo, nên chỉ cần thêm đúng một file trọng số.

---

## 2. Yêu cầu máy

| Thành phần | Phiên bản / ghi chú |
|---|---|
| Hệ điều hành | Windows 10/11 (đã kiểm thử), Linux hoặc macOS |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | ≥ 0.9 — uv tự tải Python 3.12, **không cần** cài Python riêng |
| MySQL | **8.0** (cần hỗ trợ FULLTEXT `WITH PARSER ngram`), tài khoản có quyền `CREATE DATABASE` |
| [Ollama](https://ollama.com/download) | Đang chạy và **đã có sẵn model** ghi trong `OLLAMA_MODEL` (mặc định `qwen2.5:7b`, ~4,7 GB) |
| RAM / đĩa | Khuyến nghị ≥ 16 GB RAM; ≥ 15 GB đĩa trống (torch ~3 GB, model Ollama ~5 GB, PhoBERT ~0,5 GB) |
| GPU (tuỳ chọn) | NVIDIA có driver hỗ trợ CUDA 12.8 thì Ollama và huấn luyện nhanh hơn; không có GPU vẫn chạy được, chỉ chậm hơn |

PyTorch được chọn tự động theo `pyproject.toml`: Windows lấy bản **CUDA 12.8**, Linux lấy bản **CPU**, macOS lấy bản mặc định của PyPI.

> Nên đặt thư mục dự án ở đường dẫn **không dấu, không dấu cách** (vd `D:\projects\llm-ctu`) để tránh lỗi đọc file của một số công cụ. Luôn chạy lệnh tại **thư mục gốc** dự án.

---

## 3. Cài đặt

```powershell
git clone https://github.com/SirKimCh/llm-ctu.git
cd llm-ctu
uv sync                      # tạo .venv theo uv.lock (lần đầu tải torch khá lâu)
```

Chuẩn bị model Ollama (người dùng tự làm, hệ thống **không bao giờ** tự tải model):

```powershell
ollama list                  # xem model đang có
ollama pull qwen2.5:7b       # chỉ khi chưa có — hoặc đổi OLLAMA_MODEL trong .env sang model đã có
```

Bổ sung trọng số NLU: chép `model.safetensors` vào `artifacts/nlu/` (cách A), hoặc huấn luyện theo mục 6 (cách B).

---

## 4. Cấu hình `.env`

```powershell
Copy-Item .env.example .env          # Linux/macOS: cp .env.example .env
```

Mọi thông số đọc qua `app/config.py` từ file này. Các biến thường phải sửa trên máy mới:

| Biến | Mặc định | Sửa khi |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` | `127.0.0.1`, `3306`, `root`, `123456` | Tài khoản MySQL của máy bạn khác |
| `DB_NAME` | `llm_ctu` | Muốn tên CSDL khác (app **tự tạo** nếu chưa có, collation `utf8mb4_unicode_ci`) |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama chạy ở máy/cổng khác |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Dùng model khác — tên phải khớp đúng một dòng trong `ollama list` |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Máy yếu/không GPU, câu trả lời bị hết giờ ⇒ tăng lên |
| `APP_PORT` | `8000` | Cổng 8000 bị chiếm |
| `SECRET_KEY` | giá trị mẫu | Nên đổi thành chuỗi ngẫu nhiên ≥ 32 ký tự (bắt buộc khi `APP_ENV=production`) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `admin`, `Admin@123` | Chỉ dùng để tạo tài khoản quản trị **lần đầu** |
| `BRIGHTDATA_API_TOKEN`, `BRIGHTDATA_ZONE` | trống, `mcp_unlocker` | Muốn dùng chức năng cào web. Để trống ⇒ tắt cào, import Excel vẫn chạy |

Sinh `SECRET_KEY` nhanh: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`.

> ⚠️ `.env` chứa mật khẩu và token — không commit, không gửi kèm khi nén mã nguồn.

---

## 5. Chạy — một lệnh

```powershell
uv run run.py
```

`run.py` kiểm tra lần lượt, **thiếu mục nào thì in hướng dẫn tiếng Việt và dừng** (không tự sửa, không tự tải gì):

```
[OK] .env · [OK] SECRET_KEY · [OK] MySQL · [OK] Ollama · [OK] Model · [OK] NLU · [OK] CSDL · [OK] Brightdata · [OK] Cổng
Mở trình duyệt: http://127.0.0.1:8000
```

Lần chạy đầu app tự tạo CSDL, tạo bảng và tạo tài khoản quản trị từ `.env`.

| Mã thoát | Nguyên nhân | Cách xử lý |
|:--:|---|---|
| 2 | Thiếu `.env` / thiếu hoặc sai biến / `SECRET_KEY` yếu khi production | Làm lại mục 4 |
| 3 | Không kết nối hoặc không đăng nhập được MySQL, không tạo được CSDL | Bật MySQL (Windows: `Start-Service MySQL80` bằng PowerShell quyền Admin), kiểm `DB_*` |
| 4 | Ollama chưa chạy | Mở ứng dụng Ollama hoặc chạy `ollama serve` ở cửa sổ khác |
| 5 | Không có model `OLLAMA_MODEL` | Thông báo liệt kê model đang có ⇒ sửa `.env` hoặc tự `ollama pull` |
| 6 | Thiếu file trong `artifacts/nlu/` (thường là `model.safetensors`) | Chép file trọng số hoặc huấn luyện (mục 6) |
| 7 | Cổng `APP_PORT` bị chiếm | Đổi `APP_PORT` hoặc tắt tiến trình đang dùng cổng |

Kiểm tra trạng thái khi app đang chạy: `http://127.0.0.1:8000/health`.

### Dùng thử

1. Đăng nhập `admin` / `Admin@123` (hoặc giá trị trong `.env`).
2. **Tri thức** (`/admin/knowledge`): tải **file Excel mẫu** → điền → import (lỗi được báo theo từng dòng/cột, file lỗi không lưu dòng nào); hoặc tạo job **cào URL** (cần token Brightdata) và theo dõi thanh tiến độ.
3. **Người dùng** (`/admin/users`): tạo tài khoản sinh viên. Hệ thống không có trang tự đăng ký, đổi mật khẩu hay quên mật khẩu — chỉ admin tạo tài khoản.
4. Đăng nhập bằng tài khoản vừa tạo → **Chat** (`/chat`) → hỏi, vd *"Điểm chuẩn ngành Kỹ thuật phần mềm năm 2025?"* rồi *"Còn năm 2024 thì sao?"* (lượt sau giữ lại ngành của lượt trước).

CSDL ban đầu **trống tri thức**: chưa import/cào thì chatbot trả lời "chưa có thông tin".

---

## 6. Huấn luyện lại NLU (khi không có `model.safetensors`)

```powershell
uv run --group train jupyter lab notebooks/train_nlu.ipynb
```

Hoặc mở notebook bằng VS Code / PyCharm, chọn kernel `.venv` (trước đó chạy `uv sync --group train`).

- Notebook đọc `data/nlu/{train,dev,test}.jsonl` (có sẵn trong repo), tải `vinai/phobert-base` từ HuggingFace (cần Internet; biến môi trường `HF_TOKEN` là tuỳ chọn), huấn luyện, in intent accuracy / slot F1 trên tập test và lưu vào `NLU_MODEL_DIR` (`artifacts/nlu/`).
- Chạy **Run All** từ trên xuống. GPU 6 GB mất vài phút; chỉ CPU thì lâu hơn nhiều. Trên Linux, torch mặc định là bản CPU.
- Có thể chạy trên Google Colab: upload `app/`, `data/nlu/` và notebook, chạy xong tải thư mục `artifacts/nlu/` về máy.
- Muốn sinh lại bộ dữ liệu: `uv run python -m training.build_dataset`.

Huấn luyện xong, chạy lại `uv run run.py`.

---

## 7. Triển khai VPS bằng Docker

`Dockerfile` + `docker-compose.yml` dựng đủ 3 dịch vụ: `mysql`, `ollama` (service `ollama-init` tự tải đúng `OLLAMA_MODEL` một lần nếu VPS chưa có) và `app`.

```bash
# Trên VPS (Ubuntu 22.04+, docker compose v2, khuyến nghị ≥ 4 vCPU, ≥ 16 GB RAM, ≥ 30 GB đĩa)
git clone https://github.com/SirKimCh/llm-ctu.git && cd llm-ctu
scp -r <máy-có-model>:<đường-dẫn>/artifacts/nlu/model.safetensors artifacts/nlu/   # trọng số không có trong git
cp .env.example .env && chmod 600 .env
#   sửa: APP_ENV=production, SECRET_KEY (openssl rand -base64 48),
#        MYSQL_ROOT_PASSWORD, DB_USER (không dùng root), DB_PASSWORD, ADMIN_PASSWORD,
#        SESSION_HTTPS_ONLY=true nếu đặt sau reverse proxy HTTPS
docker compose build
docker compose up -d
curl -s http://127.0.0.1:8000/health
```

Vận hành: `docker compose logs -f app` · `docker compose restart app` · `docker compose down`.
⛔ **Không** dùng `docker compose down -v` — lệnh này xoá volume, mất toàn bộ CSDL và model Ollama.
Chỉ cổng `APP_PORT` được publish; MySQL (3306) và Ollama (11434) không mở ra Internet.

---

## 8. Sự cố thường gặp

| Triệu chứng | Xử lý |
|---|---|
| `FileNotFoundError` hoặc lỗi đọc file | Chạy lệnh tại thư mục gốc dự án; chuyển dự án sang đường dẫn không dấu |
| Tiếng Việt thành `?` trong CSDL | CSDL/bảng phải là `utf8mb4_unicode_ci` — xoá CSDL `llm_ctu` rồi `uv run run.py` để app tạo lại |
| Tìm kiếm không ra kết quả dù đã import | Kiểm `SHOW VARIABLES LIKE 'ngram_token_size'` trên MySQL phải là `2` (mặc định) |
| Chat trả lời rất chậm, lần đầu càng chậm | Ollama đang nạp model / chạy CPU — bình thường; tăng `OLLAMA_TIMEOUT_SECONDS` |
| `torch.cuda.is_available()` là `False` trên Windows có GPU NVIDIA | Cập nhật driver NVIDIA (cần hỗ trợ CUDA 12.8), rồi `uv sync` lại |
| `uv sync` báo hết dung lượng | Bộ nhớ đệm uv nằm ở `.uv-cache/` trong dự án (cấu hình `[tool.uv] cache-dir`) — cần đủ chỗ trên ổ chứa dự án |
| Dựng lại CSDL từ đầu | `mysql -u root -p -e "DROP DATABASE IF EXISTS llm_ctu"` rồi `uv run run.py` (dữ liệu tri thức, người dùng, hội thoại sẽ mất) |

---

## 9. Cấu trúc thư mục

```
llm-ctu/
├── run.py                   # một lệnh: kiểm tra môi trường → chạy uvicorn
├── pyproject.toml · uv.lock # phụ thuộc (quản lý bằng uv)
├── .env.example             # mẫu cấu hình — chép thành .env
├── Dockerfile · docker-compose.yml · .dockerignore   # chỉ dùng trên VPS
├── app/
│   ├── main.py · config.py · db.py
│   ├── models/ schemas/ controllers/ services/   # MVC chia theo lớp
│   ├── views/               # Jinja2 templates
│   └── static/              # css, js, font tự host
├── notebooks/train_nlu.ipynb   # fine-tune PhoBERT (intent + slot)
├── training/                # sinh bộ dữ liệu NLU
├── data/nlu/                # train/dev/test.jsonl + labels.json
└── artifacts/nlu/           # model NLU đã huấn luyện (model.safetensors bổ sung riêng)
```

## Giấy phép

MIT — xem [LICENSE](LICENSE).
