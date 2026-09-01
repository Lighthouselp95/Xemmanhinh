# Kiến Thức Chuyên Sâu và Hướng Dẫn Cài Đặt Virtual Display Driver (VDD) Cho Windows

## 1. Cơ Sở Lý Thuyết Về Cơ Chế Hiển Thị Và Capture Trên Windows

### 1.1. Kiến trúc Desktop Window Manager (DWM) và Pipeline Dựng Hình
Trong hệ điều hành Windows, Desktop Window Manager (DWM) đóng vai trò là trình quản lý kết hợp giao diện đồ họa (compositor), chịu trách nhiệm nhận các bề mặt hình ảnh từ mọi cửa sổ ứng dụng và tổng hợp chúng vào một khung hình đệm duy nhất (framebuffer) trên bộ nhớ của card đồ họa (GPU).
Quá trình tổng hợp khung hình này phụ thuộc hoàn toàn vào xung nhịp và tín hiệu kết nối của các cổng xuất hình vật lý (Display Outputs như HDMI, DisplayPort hoặc VGA).
Khi hệ điều hành phát hiện không có bất kỳ màn hình vật lý nào được kết nối vào GPU (trạng thái Headless), DWM sẽ tự động chuyển sang cơ chế tiết kiệm điện năng hoặc đình chỉ hoàn toàn chu trình tổng hợp khung hình đồ họa vào phần cứng GPU, dẫn đến việc không có dữ liệu hình ảnh mới nào được ghi vào bộ đệm khung hình.

### 1.2. Cơ chế hoạt động của DXGI Desktop Duplication API
Thư viện dxcam sử dụng trực tiếp Desktop Duplication API thuộc tầng DirectX Graphics Infrastructure (DXGI) thông qua giao diện lập trình IDXGIOutputDuplication.
Giao diện này gắn chặt quyền truy xuất dữ liệu hình ảnh với một cổng xuất hình cụ thể (IDXGIOutput) được liên kết với một màn hình đang hoạt động.
Khi dây cáp HDMI bị rút ra khỏi cổng cắm vật lý, card đồ họa sẽ gửi tín hiệu ngắt kết nối phần cứng (Hot Plug Detect - HPD), làm cho đối tượng IDXGIOutput bị giải phóng và trở nên không hợp lệ.
Hệ quả trực tiếp là hàm lấy khung hình sẽ lập tức ném ra mã lỗi truy cập bị mất (DXGI_ERROR_ACCESS_LOST) hoặc chỉ thu thập được các mảng byte trắng/đen thuần túy chứa toàn giá trị 0x00, khiến luồng stream video gửi về client bị tối đen hoàn toàn.

### 1.3. Nguyên lý hoạt động của Virtual Display Driver (IddCx)
Để khắc phục tình trạng DWM ngừng dựng hình khi không có màn hình vật lý, Microsoft cung cấp kiến trúc Indirect Display Driver Model (IddCx) chạy ở chế độ người dùng (User-Mode Driver Framework - UMDF 2.0).
Virtual Display Driver (VDD) là một trình điều khiển ảo được xây dựng dựa trên mẫu kiến trúc IddSampleDriver của Microsoft.
Khi được cài đặt vào hệ thống, VDD sẽ đăng ký một thiết bị xuất hình ảo trực tiếp với nhân hệ điều hành (Hardware ID: Root\MttVDD) và giả lập đầy đủ các tập lệnh định danh màn hình (EDID - Extended Display Identification Data).
Hệ điều hành Windows sẽ nhận diện đây là một màn hình hiển thị tiêu chuẩn (Generic Monitor) luôn luôn được cắm cố định vào hệ thống, từ đó buộc DWM và GPU duy trì liên tục chu trình dựng hình 60fps/120fps trên bộ nhớ video mà không cần đến bất kỳ thiết bị vật lý nào gắn ngoài.

---

## 2. Quy Trình Cài Đặt Và Cấu Hình Virtual Display Driver

### 2.1. Chuẩn bị gói cài đặt
Gói cài đặt Virtual Display Driver có thể được tải tự động thông qua công cụ quản lý gói của Windows (WinGet) hoặc trích xuất từ kho mã nguồn mở VirtualDrivers/Virtual-Display-Driver:
```powershell
winget install --id=VirtualDrivers.Virtual-Display-Driver -e --accept-source-agreements --accept-package-agreements
```

Sau khi tải xong, các tệp tin cốt lõi sẽ nằm tại đường dẫn:
`%LOCALAPPDATA%\Microsoft\WinGet\Packages\VirtualDrivers.Virtual-Display-Driver_Microsoft.Winget.Source_8wekyb3d8bbwe`
- Thư mục SignedDrivers\x86\VDD: Chứa tệp điều khiển MttVDD.inf, MttVDD.dll và chữ ký số MttVDD.cat (dùng chung cho hệ điều hành Windows 64-bit AMD64/x86_64).
- Thư mục Dependencies: Chứa công cụ quản lý thiết bị Device Console (devcon.exe) và tệp cấu hình hiển thị (vdd_settings.xml).

### 2.2. Thiết lập thư mục cấu hình chuẩn
Trình điều khiển VDD yêu cầu một tệp cấu hình XML đặt tại thư mục gốc của ổ đĩa C để xác định danh sách các độ phân giải và tần số quét được hỗ trợ:
1. Tạo thư mục hệ thống: `C:\VirtualDisplayDriver`
2. Sao chép tệp `vdd_settings.xml` vào đường dẫn `C:\VirtualDisplayDriver\vdd_settings.xml`.

Nội dung chuẩn của tệp cấu hình `vdd_settings.xml`:
```xml
<?xml version='1.0' encoding='utf-8'?>
<vdd_settings>
    <monitors>
        <count>1</count>
    </monitors>
    <gpu>
        <friendlyname>default</friendlyname>
    </gpu>
    <global>
        <g_refresh_rate>60</g_refresh_rate>
        <g_refresh_rate>90</g_refresh_rate>
        <g_refresh_rate>120</g_refresh_rate>
        <g_refresh_rate>144</g_refresh_rate>
    </global>
    <resolutions>
        <resolution>
            <width>1920</width>
            <height>1080</height>
            <refresh_rate>60</refresh_rate>
        </resolution>
        <resolution>
            <width>2560</width>
            <height>1440</height>
            <refresh_rate>60</refresh_rate>
        </resolution>
    </resolutions>
    <options>
        <HardwareCursor>true</HardwareCursor>
        <SDR10bit>false</SDR10bit>
        <HDRPlus>false</HDRPlus>
        <logging>false</logging>
    </options>
</vdd_settings>
```

### 2.3. Nạp trình điều khiển và khởi tạo thiết bị
Việc cài đặt bắt buộc phải được thực thi dưới quyền Administrator thông qua 2 lệnh:

Bước 1: Nạp gói driver vào kho lưu trữ hệ thống (Driver Store):
```cmd
pnputil /add-driver "%LOCALAPPDATA%\Microsoft\WinGet\Packages\VirtualDrivers.Virtual-Display-Driver_Microsoft.Winget.Source_8wekyb3d8bbwe\SignedDrivers\x86\VDD\MttVDD.inf" /install
```

Bước 2: Tạo nút thiết bị phần cứng ảo trong cây thiết bị Windows:
```cmd
"%LOCALAPPDATA%\Microsoft\WinGet\Packages\VirtualDrivers.Virtual-Display-Driver_Microsoft.Winget.Source_8wekyb3d8bbwe\Dependencies\devcon.exe" install "%LOCALAPPDATA%\Microsoft\WinGet\Packages\VirtualDrivers.Virtual-Display-Driver_Microsoft.Winget.Source_8wekyb3d8bbwe\SignedDrivers\x86\VDD\MttVDD.inf" "Root\MttVDD"
```

Khi thực thi thành công, Windows Device Manager sẽ xuất hiện 2 thành phần mới:
- Display Adapters: Virtual Display Driver
- Monitors: Generic Monitor (VDD by MTT)

---

## 3. Hướng Dẫn Quản Lý Và Vận Hành

### 3.1. Kịch bản một chạm (One-Click Scripts)
Để tạo sự thuận tiện trong quá trình sử dụng hàng ngày, hai kịch bản tự động đã được tích hợp sẵn ngoài Desktop:
1. `Cai_Dat_Man_Hinh_Ao.bat`: Tự động xin quyền Admin, thiết lập thư mục cấu hình và cài đặt driver hoàn chỉnh chỉ trong 3 giây.
2. `Bat_Tat_Man_Hinh_Ao.bat`: Cho phép người dùng tùy chọn Bật (Enable), Tắt (Disable) hoặc Gỡ bỏ (Remove) màn hình ảo khi cần thiết.

Lệnh điều khiển bằng devcon.exe:
- Bật màn hình ảo: `devcon.exe enable "Root\MttVDD"`
- Tắt màn hình ảo: `devcon.exe disable "Root\MttVDD"`
- Gỡ bỏ hoàn toàn: `devcon.exe remove "Root\MttVDD"`

### 3.2. Kết quả đạt được với dự án Xemmanhinh
Sau khi thiết lập Virtual Display Driver, hệ thống đạt được trạng thái hoạt động độc lập hoàn toàn với phần cứng màn hình ngoài:
- Máy tính có thể hoạt động ở chế độ không đầu cắm (headless server).
- dxcam luôn bắt được khung hình liên tục ở độ phân giải 1080p với tốc độ 45fps/60fps ổn định.
- Loại bỏ triệt để hiện tượng đen màn hình khi rút dây HDMI hoặc khi màn hình vật lý chuyển sang chế độ ngủ (Display Sleep).

---

## 4. Kiến Thức Vận Hành Đồ Họa Và Tô Pô Màn Hình Windows (Display Topology)

### 4.1. Lý thuyết về kiến trúc hiển thị của Windows DWM và DXGI
Trong hệ điều hành Windows, cách thức quản lý màn hình và luồng render của Desktop Window Manager (DWM) ảnh hưởng trực tiếp đến kết quả của API chụp màn hình DXGI Desktop Duplication (`IDXGIOutputDuplication`):

1. **Chế độ Duplicate (Nhân bản / Clone - Windows + P -> Duplicate)**:
   - DWM và card đồ họa GPU xử lý toàn bộ các màn hình (màn hình thật và màn hình ảo VDD) như một không gian làm việc duy nhất (Single Viewport / Swapchain).
   - Tín hiệu hình ảnh từ GPU được sao chép và phát đồng thời ra cả cổng HDMI vật lý và cổng ảo của driver VDD.
   - DXGI Desktop Duplication API nhận diện toàn bộ cụm màn hình này là một cổng xuất hình duy nhất (`Output 0`).
   - Vì lý do đó, khi ở chế độ Duplicate, danh sách chọn màn hình trên giao diện Web chỉ hiển thị 1 màn hình duy nhất. Đây là hành vi đồ họa tiêu chuẩn và chính xác của Windows.
   - Ưu điểm của chế độ Duplicate: Người dùng không cần phải thực hiện thao tác chuyển đổi màn hình thủ công. Khi cắm hoặc rút dây HDMI, toàn bộ các cửa sổ phần mềm và luồng stream trên điện thoại đều giữ nguyên vị trí, không bị gián đoạn hay nhảy màn hình.

2. **Chế độ Extend (Mở rộng không gian làm việc - Windows + P -> Extend)**:
   - Windows tách biệt bộ nhớ đồ họa thành hai không gian màn hình hoàn toàn độc lập (Desktop 1 và Desktop 2).
   - Card đồ họa phân bổ hai cổng xuất hình riêng biệt: `Output 0` (Màn hình chính) và `Output 1` (Màn hình ảo VDD).
   - Lúc này, chức năng quét màn hình trên Server và Web Client sẽ nhận diện đầy đủ 2 màn hình riêng biệt trong menu chọn màn hình phát (Display Selector), cho phép người dùng tự do lựa chọn stream Desktop 1 hoặc Desktop 2 theo ý muốn.

3. **Chế độ Headless (Rút hẳn cáp màn hình thật)**:
   - Khi cáp HDMI vật lý bị ngắt kết nối, Windows tự động thăng cấp màn hình ảo VDD (`Generic Monitor VDD by MTT`) thành màn hình chính duy nhất (`Primary Display / Output 0`).
   - dxcam và bộ mã hóa H.264 tự động bắt lấy khung hình từ VDD mà không cần bất kỳ can thiệp nào từ phía người dùng.

## 5. Cơ chế xử lý ngắt kết nối DXGI (0x887A0026) và Khắc phục treo luồng khi Rút Cáp Nóng

### 5.1. Lý thuyết về vòng đời Desktop Duplication khi thay đổi Topology hiển thị
Khi một màn hình vật lý (như cáp HDMI/DisplayPort) bị ngắt kết nối đột ngột trong khi hệ thống đang chạy chế độ Duplicate hoặc Extend:
- Desktop Window Manager (DWM) của Windows thực hiện tái lập phiên desktop đồ họa sang các cổng hiển thị còn lại (màn hình ảo Virtual Display Driver - VDD MTT).
- Giao diện `IDXGIOutputDuplication` đang được gắn với cổng màn hình cũ lập tức bị Windows thu hồi quyền truy cập. Lệnh `AcquireNextFrame` từ driver đồ họa sẽ trả về mã lỗi `HRESULT 0x887A0026` (`DXGI_ERROR_ACCESS_LOST`).
- Mọi luồng đồ họa đang cố gắng truy cập cổng cũ sẽ nhận mã lỗi từ chối quyền truy cập (`E_ACCESSDENIED 0x80070005` hoặc `E_FAIL 0x80004005`) cho đến khi chuyển giao hoàn tất.

### 5.2. Nguyên lý Chống Treo Vô Hạn (Non-blocking Frame Fetching)
Trong các thư viện chụp màn hình như dxcam, hàm `get_latest_frame()` sử dụng vòng lặp vô hạn `while True:` để chờ sự kiện có khung hình mới (`__frame_available`). Khi cổng xuất hình bị ngắt đột ngột:
- Luồng nội bộ của thư viện rơi vào chu trình phục hồi tự động nhưng không thể tìm thấy output cũ, khiến sự kiện khung hình mới không bao giờ được kích hoạt.
- Nếu không có timeout cứng ở tầng ứng dụng, luồng chụp của server sẽ bị kẹt vĩnh viễn trong hàm lấy khung hình, vô hiệu hóa toàn bộ cơ chế phát hiện mất kết nối (watchdog timer).
- Giải pháp tiêu chuẩn: Ứng dụng phải tự quản lý thời gian chờ của sự kiện (`event.wait(timeout=0.05)`). Khi hết thời gian chờ mà không có khung hình mới, hàm phải trả về kết quả rỗng (`None`) để nhường quyền điều khiển cho luồng giám sát. Khi số lần trả về rỗng vượt ngưỡng thời gian quy định (0.8 giây), hệ thống chủ động giải phóng toàn bộ tài nguyên DirectX cũ, gắn lại quyền Desktop Session (`SetThreadDesktop(OpenInputDesktop(...))`) và khởi tạo lại camera trên màn hình ảo VDD MTT.

### 5.3. Quản lý vòng đời đối tượng COM và Dynamic Output Clamping khi Hotplug liên tiếp
Khi người dùng cắm và rút cáp HDMI nhiều chu kỳ liên tiếp (Rút -> Cắm lại -> Rút tiếp):
- Rò rỉ đối tượng COM và Windows DWM Refusal:
  Mỗi lần thay đổi cấu hình hiển thị, các đối tượng COM giao tiếp cấp thấp trong dxcam như ID3D11Device, ID3D11DeviceContext và IDXGIOutputDuplication phải được giải phóng hoàn toàn. Nếu các wrapper Python hoặc singleton nội bộ còn giữ tham chiếu tham lam, Windows DWM sẽ ghi nhận phiên làm việc cũ chưa đóng và từ chối khởi tạo phiên Desktop Duplication mới (trả về lỗi khởi tạo hoặc camera bị rỗng). Do đó, quy trình reset cần duyệt qua toàn bộ dictionary chứa devices và outputs của dxcam, gán cờ giải phóng, xóa sạch singleton và ép chạy bộ gom rác gc.collect() 2 lần tường minh để giải phóng tài nguyên ở tầng nhân đồ họa.
- Dynamic Output Clamping (Khống chế chỉ số màn hình động):
  Số lượng màn hình thực tế (outputs) thay đổi theo từng thời điểm cắm/rút. Khi đang cắm cả cáp HDMI và driver ảo VDD, hệ thống có 2 outputs (index 0 và index 1). Nếu đang ghi hình từ output 1 mà người dùng rút cáp HDMI, Windows chuyển về trạng thái chỉ còn 1 output duy nhất (index 0). Nếu server giữ nguyên chỉ số output cũ mà không kiểm tra, lệnh tạo camera dxcam.create(output_idx=1) sẽ lập tức vấp phải ngoại lệ IndexError do vượt quá số lượng màn hình khả dụng. Cơ chế Dynamic Output Clamping tự động truy vấn số lượng output thực tế trên adapter mới, so sánh và hạ target_idx về 0 an toàn nếu chỉ số yêu cầu vượt quá giới hạn, đồng thời đồng bộ lại trạng thái nội bộ.
- Cooldown Backoff cho Windows DWM:
  Sau thao tác cắm hoặc rút cáp, hệ điều hành Windows và driver đồ họa mất một khoảng thời gian ngắn (từ 0.3s đến 0.5s) để dàn xếp lại bảng phân giải, định vị lại vị trí cửa sổ và cập nhật topology. Việc áp dụng thời gian chờ cooldown backoff 0.5s trước khi khởi tạo lại camera giúp tránh việc truy vấn khi DWM đang trong trạng thái chuyển tiếp, đảm bảo phiên bắt hình luôn được thiết lập thành công và ổn định lâu dài.

### 5.4. Cơ chế Fast 0ms Health-Check Detection và Xử lý An Toàn Con Trỏ COM Khi Ngắt Kết Nối
Trong các kịch bản cắm/rút cáp HDMI thực tế, việc tối ưu hóa tốc độ nhận diện sự cố và đảm bảo an toàn con trỏ COM cấp thấp đóng vai trò then chốt:
- Xử lý an toàn con trỏ COM (Output.update_desc Protection):
  Khi một cổng hiển thị bị ngắt kết nối đột ngột trong DirectX, đối tượng IDXGIOutput bị hủy và biến thành con trỏ rỗng (None/nullptr). Trong thư viện dxcam, hàm cập nhật mô tả output (Output.update_desc) mặc định gọi trực tiếp self.output.GetDesc() mà không kiểm tra tính hợp lệ của con trỏ. Khi xảy ra ngắt kết nối, lệnh này phát sinh ngoại lệ AttributeError ('NoneType' object has no attribute 'GetDesc') làm sụp đổ hoàn toàn luồng capture nền (DXCamera thread). Cơ chế monkey-patch an toàn chặn trước điều kiện self.output is None, bỏ qua gọi hàm native khi con trỏ đã giải phóng và cập nhật trạng thái lỗi có kiểm soát, ngăn chặn crash luồng capture.
- Cơ chế Fast 0ms Health-Check Detection (_is_camera_alive):
  Thay vì dựa vào cơ chế đếm thời gian timeout tĩnh (chờ mất frame 0.8s - 1.5s mới phát hiện camera ngừng hoạt động), hệ thống triển khai hàm kiểm tra sức khỏe tức thì _is_camera_alive(). Hàm này trực tiếp kiểm tra các cờ nội bộ của camera (is_stopped, thread.is_alive, is_released) ngay trong mỗi vòng lặp capture. Khi luồng capture của dxcam vừa dừng hoặc gặp sự cố hotplug, server phát hiện ngay lập tức với độ trễ 0ms mà không cần đợi timeout mất frame.
- Tối ưu hóa chu trình tái kết nối dưới 100ms: Bằng cách kết hợp Fast Health-Check 0ms, giảm watchdog timeout xuống 0.2s, rút ngắn thời gian cooldown xuống 0.05s (50ms) và tối ưu retry delay về 50ms, hệ thống có thể hoàn tất toàn bộ chu trình: dọn dẹp COM, tái khởi tạo camera DXGI trên màn hình ảo VDD MTT, cấu hình lại bộ mã hóa H.264 và gửi keyframe mới trong tổng thời gian dưới 100ms, mang lại trải nghiệm chuyển tiếp mượt mà và liền mạch tuyệt đối cho người dùng.

### 5.5. Cơ chế Fail-Fast Handover giữa Thư viện Chụp màn hình và Server Orchestration
Trong các hệ thống truyền phát hình ảnh thời gian thực, việc phân định rõ trách nhiệm xử lý lỗi giữa thư viện capture cấp thấp (dxcam) và tầng điều phối dịch vụ (Server Orchestration) là yếu tố quyết định tính ổn định khi xảy ra biến động phần cứng (Display Hotplug):
- Hạn chế của cơ chế tự phục hồi nội bộ trong thư viện capture:
  Khi phát sinh sự kiện ngắt kết nối màn hình (DXGI_ERROR_ACCESS_LOST 0x887A0026), thư viện dxcam mặc định kích hoạt chu trình tự phục hồi nội bộ (DXCamera._recover_output -> DisplayRecoveryHandler -> StageSurface.rebuild). Tuy nhiên, do toàn bộ Direct3D Device và Output Duplication đã bị Windows DWM hủy bỏ, các con trỏ thiết bị (device, device.device) đều trở thành None. Lệnh khởi tạo lại bề mặt texture (device.device.CreateTexture2D) lập tức ném ra ngoại lệ Unhandled exception AttributeError: 'NoneType' object has no attribute 'CreateTexture2D', làm crash hoặc kẹt cứng luồng capture nền. Ngoài ra, cơ chế nội bộ của thư viện không có khả năng quét lại toàn bộ topology hiển thị hay tự động chuyển đổi sang màn hình ảo VDD.
- Nguyên lý Fail-Fast Handover:
  Thay vì để thư viện capture loay hoay tự phục hồi trong vô vọng và xung đột tài nguyên, hệ thống áp dụng nguyên lý Fail-Fast:
  1. Chặn đứng chu trình tự phục hồi nội bộ: Bản vá monkey-patch tại DXCamera._recover_output lập tức gán is_capturing = False và cho phép luồng capture dừng lại êm dịu mà không cố gắng rebuild hay truy xuất lại các con trỏ COM đã chết.
  2. Bảo vệ bề mặt StageSurface: Bản vá tại StageSurface.rebuild bổ sung kiểm tra hợp lệ của device và device.device trước khi thực hiện gọi CreateTexture2D, loại bỏ hoàn toàn nguy cơ crash với lỗi NoneType.
  3. Bàn giao toàn quyền điều phối cho Server: Server phát hiện ngay lập tức luồng capture đã dừng thông qua hàm _is_camera_alive() với độ trễ 0ms. Tầng Server Orchestration - nơi có đầy đủ bức tranh toàn cảnh về phần cứng, COM Singleton, danh sách màn hình và encoder - sẽ chủ động dọn sạch DXFactory cũ, khởi tạo lại phiên làm việc mới trên màn hình khả dụng (màn hình chính hoặc màn hình ảo VDD MTT) và cung cấp luồng video liền mạch chỉ trong 50ms - 100ms.
- Lợi ích vận hành:
  Loại bỏ hoàn toàn tình trạng client bị rơi vào trạng thái connecting kéo dài, triệt tiêu xung đột vòng đời tài nguyên DirectX giữa server và thư viện, đảm bảo quy trình phục hồi diễn ra dứt khoát, chuẩn xác và tức thì.

---

## 6. Tài Liệu Thiết Kế Mở Rộng Hệ Thống (Design Document)

### 6.1. Tổng kết thành tựu kiến trúc Fail-Fast Handover và Instant Recovery (<100ms)
Kiến trúc Fail-Fast Handover cùng quy trình Instant Recovery đã giải quyết trọn vẹn các thách thức cố hữu của việc chụp màn hình thời gian thực trên môi trường Windows Desktop khi xảy ra biến động phần cứng:
- Loại bỏ triệt để điểm nghẽn tự phục hồi nội bộ: Bằng cách vô hiệu hóa chu trình DisplayRecoveryHandler của thư viện cấp thấp khi bắt gặp mã lỗi DXGI_ERROR_ACCESS_LOST (0x887A0026), hệ thống ngăn ngừa các lỗi truy cập con trỏ rỗng (NoneType CreateTexture2D, GetDesc) và không để luồng capture bị kẹt vô hạn.
- Cơ chế giám sát 0ms (Fast Health-Check): Server nhận biết trạng thái dừng của camera ngay trong vòng lặp chụp thông qua việc kiểm tra các cờ nội bộ thay vì phải dựa vào bộ đếm thời gian mất khung hình thụ động.
- Quy trình dọn dẹp và tái khởi tạo nguyên tử (Atomic Reset & Re-init): Thực hiện giải phóng sạch sẽ toàn bộ các đối tượng COM đồ họa, ép thu hồi rác bộ nhớ hai lần (gc.collect()), khởi tạo lại DXFactory và gắn kết với cổng hiển thị khả dụng trong thời gian kỷ lục dưới 100ms.
- Hiệu năng thực tế: Hệ thống duy trì tốc độ truyền phát video ổn định từ 35-38+ FPS liên tục, bảo toàn chất lượng hình ảnh và độ trễ thấp qua nhiều chu kỳ rút/cắm cáp HDMI liên tiếp mà không phát sinh bất kỳ ngoại lệ nào.

### 6.2. Thiết kế kiến trúc mở rộng cho Đa GPU / Đa Thiết bị (Multi-Device / Multi-GPU Adapter Enumeration)
Trong các môi trường đồ họa phức tạp với nhiều card đồ họa (ví dụ hệ thống có iGPU Intel/AMD tích hợp và dGPU NVIDIA rời, hoặc nhiều card rời cắm song song), kiến trúc cần mở rộng cơ chế liệt kê và phân bổ tài nguyên để tối ưu hiệu năng:
- Cơ chế quét và lập chỉ mục phần cứng (Adapter Topology Discovery):
  Hệ thống sử dụng IDXGIFactory1::EnumAdapters1 để thu thập toàn bộ danh sách card đồ họa hiện có trong máy. Mỗi adapter được đánh giá dựa trên các tiêu chí: loại phần cứng (Hardware vs Software/WARP), bộ nhớ video chuyên dụng (Dedicated Video Memory - VRAM), và sự hiện diện của các cổng xuất hình (Outputs/Monitors).
- Ma trận ánh xạ Display - Adapter:
  Mỗi màn hình vật lý hoặc ảo đều gắn liền với một adapter đồ họa cụ thể. Khi khởi tạo phiên Desktop Duplication, server xác định chính xác adapter sở hữu màn hình mục tiêu (thông qua EnumOutputs) để tạo Direct3D Device tương ứng trên đúng card đồ họa đó, tránh hiện tượng sao chép bộ nhớ chéo adapter (Cross-adapter Copy) gây suy giảm băng thông PCIe.
- Tận dụng bộ mã hóa phần cứng theo GPU (Hardware Encoder Binding):
  Nếu màn hình nằm trên card NVIDIA, server ưu tiên định tuyến khung hình trực tiếp tới bộ mã hóa NVENC (h264_nvenc). Nếu màn hình kết nối qua cổng iGPU Intel, server tự động linh hoạt chuyển giao sang Intel QuickSync Video (h264_qsv) hoặc AMD AMF (h264_amf), từ đó giảm thiểu việc trung chuyển dữ liệu khung hình thô qua CPU RAM.

### 6.3. Thiết kế cơ chế bao hàm toàn diện cho các Cấu hình Hiển thị (Display Topologies)
Để đảm bảo trải nghiệm đồng nhất và tự động hóa cao nhất, hệ thống thiết lập các quy tắc xử lý chuyên sâu cho từng trạng thái tô pô màn hình:

1. Chế độ Duplicate (Nhân bản / Clone):
- Cơ chế Fallback tự động: Trong chế độ Duplicate, Windows DWM xem toàn bộ cụm màn hình (màn hình chính và màn hình ảo VDD) là một Viewport duy nhất dưới cổng Output 0. Khi một trong các màn hình (ví dụ cáp HDMI) bị rút đột ngột, DWM tự động chuyển tải khung hình còn lại qua VDD mà không làm thay đổi cấu trúc swapchain. Server phát hiện sự chuyển tiếp thông qua tín hiệu ngắt truy cập và lập tức gắn kết lại phiên bắt hình vào Output 0 đang hoạt động chỉ trong một chu kỳ ngắn.
- Bảo toàn tỷ lệ khung hình (Aspect Ratio Preservation): Khi có sự sai lệch độ phân giải gốc giữa màn hình vật lý và màn hình ảo, DWM sẽ áp dụng phương pháp tỷ lệ theo tỷ lệ chuẩn hoặc căn giữa (Letterboxing/Pillarboxing). Server tự động đọc lại kích thước khung hình sau biến cố để cấu hình lại kích thước mã hóa (width/height) cho bộ encoder H.264, tránh làm méo mó hình ảnh truyền tới thiết bị client.

2. Chế độ Extend (Mở rộng không gian làm việc):
- Cơ chế liệt kê động danh sách màn hình trên toàn hệ thống (Dynamic Display Enumeration): Khi chạy ở chế độ Extend, mỗi màn hình tạo thành một không gian desktop độc lập tương ứng với các chỉ số Output 0, Output 1,... Server cung cấp danh sách mô tả chi tiết của từng màn hình (tên thiết bị, độ phân giải, tọa độ làm việc) qua giao thức WebSocket cho client.
- Xử lý lệnh chuyển màn hình thời gian thực (Realtime Screen Switching): Client có thể gửi thông điệp yêu cầu đổi màn hình đích bất kỳ lúc nào. Luồng điều phối của server sẽ tạm dừng luồng bắt hình hiện tại, giải phóng camera cũ một cách an toàn, tạo camera mới trên chỉ số output được yêu cầu và kích hoạt gửi một keyframe IDR tức thì để client dựng lại toàn bộ giao diện mà không phải tải lại trang web.
- Cơ chế tự động dồn màn hình (Auto-rebalance): Khi một màn hình phụ đang được chọn để stream bất ngờ bị rút cáp, số lượng output khả dụng bị giảm đi. Cơ chế Dynamic Output Clamping sẽ tự động phát hiện chỉ số hiện tại vượt quá giới hạn và lập tức dồn luồng capture về màn hình khả dụng gần nhất (thông thường là Output 0 / Màn hình chính hoặc Màn hình ảo VDD), bảo đảm luồng phát không bao giờ bị gián đoạn hay crash.

3. Chế độ Headless (Màn hình ảo thuần túy):
- Tự động phát hiện và kích hoạt VDD: Khi máy tính khởi động hoặc khi tất cả các màn hình vật lý đều bị ngắt kết nối, server sử dụng các hàm API hệ thống (EnumDisplayDevices, GetSystemMetrics) để kiểm tra tổng số màn hình hoạt động. Nếu phát hiện hệ thống đang ở trạng thái không có màn hình, server kích hoạt gọi lệnh quản lý thiết bị (thông qua devcon hoặc dịch vụ nền) để bật driver Virtual Display Driver (Root\MttVDD).
- Đảm bảo DWM duy trì chu trình dựng hình: VDD cung cấp thông số EDID hoàn chỉnh cho Windows, giúp DWM liên tục tổng hợp giao diện ở tốc độ 60fps mà không rơi vào trạng thái ngủ sâu (Display Sleep/Idle Suspension), phục vụ trọn vẹn mục đích làm máy chủ hiển thị không đầu cắm (headless remote server).

### 6.4. Cơ chế xử lý âm thanh đồng bộ (WASAPI Audio Loopback Transition) khi cổng HDMI Audio chuyển giao về Loa tích hợp (Speakers)
Biến động phần cứng khi rút cáp HDMI không chỉ tác động đến hình ảnh mà còn làm thay đổi toàn bộ kiến trúc âm thanh của hệ điều hành:
- Nguyên nhân gián đoạn âm thanh: Cổng HDMI truyền tải cả tín hiệu âm thanh kỹ thuật số (HDMI Audio Device). Khi rút cáp, thiết bị âm thanh HDMI Endpoint đang được Windows chọn làm mặc định sẽ bị vô hiệu hóa hoàn toàn, làm sụp đổ luồng WASAPI Loopback Capture đang thu thập âm thanh trên thiết bị đó.
- Cơ chế chuyển giao thiết bị mặc định (Audio Endpoint Fallback): Windows Audio Service tự động chuyển thiết bị âm thanh mặc định về Loa tích hợp (Speakers / Realtek Audio) hoặc tai nghe cắm sẵn.
- Tái kích hoạt luồng thu âm thanh tự động (Automatic Audio Loopback Recovery):
  1. Tầng capture âm thanh (dựa trên WASAPI / soundcard library) liên tục giám sát trạng thái thu mẫu. Khi bắt gặp sự cố đứt gãy luồng hoặc ngoại lệ mất thiết bị (AUDCLNT_E_DEVICE_INVALIDATED), luồng capture âm thanh sẽ bắt lỗi cục bộ mà không làm ảnh hưởng đến luồng truyền video.
  2. Hệ thống áp dụng chu trình tái kết nối nhanh: Quét lại danh sách Audio Endpoints qua giao diện IMMDeviceEnumerator, xác định thiết bị render mặc định mới của hệ thống (eRender, eMultimedia).
  3. Mở lại phiên WASAPI Loopback Capture trên thiết bị mới, đồng bộ lại tỷ lệ lấy mẫu (Sample Rate 48kHz) và tiếp tục đẩy các gói tin âm thanh PCM vào hàng đợi WebSocket gửi tới client. Toàn bộ quá trình chuyển giao âm thanh diễn ra trong suốt và hoàn toàn độc lập với luồng video.