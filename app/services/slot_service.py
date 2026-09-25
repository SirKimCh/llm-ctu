import re

from app.services.text_service import fold, normalize_text

MAJOR_CATALOG = (
    "Giáo dục mầm non", "Giáo dục Tiểu học", "Giáo dục Công dân", "Giáo dục Thể chất", "Sư phạm Toán học",
    "Sư phạm Tin học", "Sư phạm Vật lý", "Sư phạm Hóa học", "Sư phạm Sinh học", "Sư phạm Ngữ văn", "Sư phạm Lịch sử",
    "Sư phạm Địa lý", "Sư phạm Tiếng Anh", "Sư phạm Tiếng Pháp", "Sư phạm Khoa học tự nhiên", "Ngôn ngữ Anh",
    "Ngôn ngữ Pháp", "Triết học", "Văn học", "Kinh tế", "Chính trị học", "Xã hội học", "Tâm lý học giáo dục", "Báo chí",
    "Truyền thông đa phương tiện", "Thông tin - thư viện", "Quản trị kinh doanh", "Marketing", "Kinh doanh quốc tế",
    "Kinh doanh thương mại", "Thương mại điện tử", "Tài chính – Ngân hàng", "Công nghệ tài chính", "Kế toán", "Kiểm toán",
    "Luật", "Luật kinh tế", "Sinh học", "Công nghệ sinh học", "Sinh học ứng dụng", "Hóa học", "Khoa học môi trường",
    "Khoa học dữ liệu", "Toán ứng dụng", "Thống kê", "Khoa học máy tính", "Mạng máy tính và truyền thông dữ liệu",
    "Kỹ thuật phần mềm", "Hệ thống thông tin", "Kỹ thuật máy tính", "Trí tuệ nhân tạo", "Công nghệ thông tin",
    "An toàn thông tin", "Công nghệ kỹ thuật hóa học", "Quản lý công nghiệp", "Logistics và quản lý chuỗi cung ứng",
    "Kỹ thuật cơ khí", "Kỹ thuật cơ điện tử", "Kỹ thuật ô tô", "Kỹ thuật điện", "Kỹ thuật điện tử – viễn thông",
    "Kỹ thuật y sinh", "Kỹ thuật điều khiển và tự động hóa", "Kỹ thuật vật liệu", "Kỹ thuật môi trường", "Vật lý kỹ thuật",
    "Công nghệ thực phẩm", "Công nghệ sau thu hoạch", "Công nghệ chế biến thủy sản", "Kiến trúc", "Quy hoạch vùng và đô thị",
    "Kỹ thuật xây dựng", "Kỹ thuật xây dựng công trình giao thông", "Kỹ thuật cấp thoát nước", "Quản lý xây dựng",
    "Khoa học đất", "Chăn nuôi", "Nông học", "Khoa học cây trồng", "Bảo vệ thực vật", "Kinh doanh nông nghiệp",
    "Kinh tế nông nghiệp", "Nuôi trồng thủy sản", "Bệnh học thủy sản", "Quản lý thủy sản", "Thú y", "Hóa dược", "Du lịch",
    "Quản trị dịch vụ du lịch và lữ hành", "Quản lý tài nguyên và môi trường", "Kinh tế tài nguyên thiên nhiên",
    "Quản lý đất đai",
)
MAJOR_ABBREVIATIONS = {
    "CNTT": "Công nghệ thông tin",
    "HTTT": "Hệ thống thông tin",
    "KTPM": "Kỹ thuật phần mềm",
    "KHMT": "Khoa học máy tính",
    "ATTT": "An toàn thông tin",
    "QTKD": "Quản trị kinh doanh",
    "KHDL": "Khoa học dữ liệu",
    "CNSH": "Công nghệ sinh học",
    "TMĐT": "Thương mại điện tử",
    "TCNH": "Tài chính – Ngân hàng",
}
METHOD_KEYWORDS = (
    (("hoc ba",), "học bạ"),
    (("v-sat", "vsat"), "V-SAT"),
    (("tuyen thang", "uu tien"), "tuyển thẳng, ưu tiên xét tuyển"),
    (("phuong thuc 5",), "phương thức 5"),
    (("thpt", "diem thi"), "điểm thi tốt nghiệp THPT"),
)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
WORD = re.compile(r"\w+")
FOLLOW_UP_FILLERS = frozenset(
    "con vay the thi sao nao ra nhu nam nganh cua voi va nhe a ha do duoc khong xet tuyen phuong thuc hoc cho minh hoi em toi ban oi".split()
)


ABBREVIATION_KEYS = {fold(short): full for short, full in MAJOR_ABBREVIATIONS.items()}


def canonical_major(value: str | None, known: list[str]) -> str | None:
    if not value:
        return None
    key = fold(value)
    padded = f" {key} "
    for short, full in ABBREVIATION_KEYS.items():
        if f" {short} " in padded:
            return next((major for major in known if fold(major) == fold(full)), full)
    matches = [major for major in known if f" {fold(major)} " in padded]
    return max(matches, key=len) if matches else None


def canonical_year(value: str | None) -> int | None:
    match = YEAR.search(value or "")
    return int(match.group()) if match else None


def _method_by_keyword(key: str) -> tuple[str, str] | None:
    for keywords, method in METHOD_KEYWORDS:
        for keyword in keywords:
            if keyword in key:
                return keyword, method
    return None


def canonical_method(value: str | None, text: str = "") -> str | None:
    found = _method_by_keyword(fold(value or "")) or _method_by_keyword(fold(text))
    if found:
        return found[1]
    return normalize_text(value) if value else None


def extract_slots(nlu_slots: dict[str, str], text: str, known: list[str]) -> dict:
    raw_major = nlu_slots.get("nganh_hoc")
    candidates = {
        "nganh_hoc": canonical_major(raw_major, known) or canonical_major(text, known) or (normalize_text(raw_major) if raw_major else None),
        "nam": canonical_year(nlu_slots.get("nam")) or canonical_year(text),
        "phuong_thuc": canonical_method(nlu_slots.get("phuong_thuc"), text) if nlu_slots.get("phuong_thuc") else None,
    }
    return {name: value for name, value in candidates.items() if value}


def follow_up_slots(text: str, known: list[str]) -> dict:
    """Câu nối tiếp chỉ gồm ngành/năm/phương thức và từ đệm ("còn năm 2023 thì sao?") ⇒ các slot đó, ngược lại ⇒ {}."""
    key = fold(text)
    covered = set(FOLLOW_UP_FILLERS) | set(ABBREVIATION_KEYS)
    slots: dict = {}
    if major := canonical_major(text, known):
        slots["nganh_hoc"] = major
        covered |= set(WORD.findall(fold(major)))
    if year := canonical_year(text):
        slots["nam"] = year
        covered.add(str(year))
    if method := _method_by_keyword(key):
        slots["phuong_thuc"] = method[1]
        covered |= set(WORD.findall(method[0]))
    if not slots or set(WORD.findall(key)) - covered:
        return {}
    return slots
