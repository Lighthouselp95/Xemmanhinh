# KNOWLEDGE - Encoder Tuning

## CRF (Constant Rate Factor) - libx264
- Thang 0-51: 0=lossless, 18=visually lossless, 23=mặc định ffmpeg, 51=tệ nhất
- CRF thấp hơn = chất lượng cao hơn = bitrate cao hơn
- Cứ giảm 6 đơn vị CRF ≈ bitrate tăng gấp đôi
- CRF 18: ~12-15Mbps cho 1080p45 motion cao
- CRF 20: ~6-8Mbps cho 1080p45 (nén mạnh, dễ banding)

## CQ (Constant Quality) - NVENC
- Tương tự CRF nhưng của NVENC: thang 1-51
- cq=18 ≈ CRF=18 (visually lossless)
- Dùng với rc=vbr (không có b) → encoder tự phân bổ bitrate
- Không dùng rc=constqp vì QP cố định không thích nghi theo frame

## Keyint (GOP size)
- Khoảng cách giữa 2 keyframe (I-frame)
- Keyint lớn = ít I-frame = ít spike bitrate = mượt hơn trên network
- Nhưng seek chậm hơn (phải decode từ I-frame gần nhất)
- Client mới kết nối: dùng forced-idr riêng, không phụ thuộc keyint
- 1080p45: keyint=120 (2.7s) là cân bằng giữa smooth và seek

## bf=0 (No B-frames)
- B-frames cần reference cả frame trước và sau → reorder → latency
- Tắt B-frames: encode/decode theo thứ tự, không cần buffer reorder
- Phù hợp streaming low-latency

## rc-lookahead=0
- libx264 nhìn trước N frame để quyết định phân bổ bit
- rc-lookahead > 0: chất lượng tốt hơn nhưng latency cao hơn
- rc-lookahead=0: không nhìn trước, latency thấp nhất

## AQ (Adaptive Quantization)
- **spatial-aq**: phân bổ bit theo không gian (vùng phẳng/tối ưu tiên bit hơn)
  - ON: giảm banding vùng tối, nhưng gradient có thể bị banding
  - OFF: gradient mượt hơn, nhưng vùng tối có thể bị block
- **temporal-aq**: phân bổ bit cho vùng chuyển động
  - ON: motion area được cấp thêm bit → ít artifacts khi chuyển động
- **aq-strength**: 1-15, thấp = nhẹ nhàng, cao = mạnh (dễ gây artifacts)

## Bitrate tham khảo 1080p45
- CRF 18: ~12-15Mbps (visually lossless)
- CRF 20: ~6-8Mbps (good quality, slight compression)
- CRF 23: ~3-5Mbps (mặc định, thấy rõ artifacts)
## Chống banding trong video streaming (tổng hợp từ nhiều nguồn)

### Nguyên nhân gốc rễ
- **8-bit 4:2:0**: chỉ có 256 mức màu + chroma giảm 1/4 độ phân giải → gradient bị chia thành bậc
- **Bitrate thấp**: encoder phải nén mạnh, bỏ chi tiết ở vùng phẳng
- **Chroma subsampling**: màu sắc bị lấy mẫu thưa, gây banding màu đặc biệt rõ ở vùng gradient

### Các kỹ thuật chống banding

#### 1. Tăng bitrate / giảm CRF
- Cách đơn giản nhất, hiệu quả cao nhất với banding do nén
- CRF 14-16 cho kết quả tốt hơn CRF 18-20 rõ rệt
- Đánh đổi: tăng CPU load và network bandwidth

#### 2. Adaptive Quantization (AQ) - libx264
- `aq-mode=1`: variance AQ (mặc định), phân bổ bit theo độ phức tạp không gian
- `aq-mode=2`: auto-variance AQ, thích nghi theo từng frame
- `aq-mode=3`: auto-variance với bias cho cảnh tối (dark scene bias)
- `aq-strength=0.80-1.30` cho mode 1/2
- `aq-strength=0.60-0.85` cho mode 3
- Tăng AQ strength giúp vùng phẳng giữ được grain/dither, giảm banding

#### 3. Deblock filter - libx264
- `--deblock alpha:beta`: kiểm soát bộ lọc khử block
- Giá trị âm (-2:-2 đến -3:-3): giữ chi tiết, giảm blur nhưng có thể tăng blocking
- Giá trị dương (1:1): mượt hơn nhưng có thể blur
- Animation: `deblock 1:1`
- Live action: `deblock -2:-2` đến `0:0`

#### 4. Psycho-visual RDO - libx264
- `psy-rd=rdo:trellis`: làm sắc nét hình ảnh psycho-visually
- `psy-rd=1.00:0` là cài đặt phổ biến (psy-trellis thường bỏ vì dễ gây hại)
- Animation: `psy-rd=0.60-0.90`
- Live action: `psy-rd=0.95-1.10`

#### 5. Dithering trước encode
- Thêm nhiễu nhẹ lên frame gốc trước khi encode
- Phá vỡ các bậc màu liên tiếp, mắt thấy mượt hơn
- Cường độ thường ±1-2 pixel
- Có thể làm tăng bitrate nhẹ nhưng giảm banding đáng kể

#### 6. NVENC-specific settings
- `spatial-aq=1`: phân bổ bit cho vùng phẳng/smooth surfaces
- `temporal-aq=1`: phân bổ bit cho vùng chuyển động
- `aq-strength=1-15`: cường độ AQ (cao = mạnh)
- `rc=vbr` + `cq=X`: VBR với quality target
- `rc=cq`: constant quality mode (yêu cầu b=0, maxrate=0, bufsize=0)
- `preset=p5-p7`: cân bằng giữa tốc độ và chất lượng
- `tune=hq` hoặc `tune=ll`: high quality hoặc low latency

#### 7. 10-bit encoding
- 10-bit có 1024 mức màu → giảm banding gần như hoàn toàn
- **Không tương thích WebCodecs/Broadway** trên phone
- Chỉ dùng được nếu client hỗ trợ decode 10-bit
- NVENC HEVC hỗ trợ 10-bit nhưng H264 thường không

#### 8. Chroma QP offset - libx264
- `chroma-qp-offset`: điều chỉnh QP cho chroma
- Giá trị âm: cấp thêm bit cho chroma → màu sắc đẹp hơn
- Mặc định: -2 cho 4:2:0

### Lưu ý quan trọng
- Không có cách nào hoàn toàn loại bỏ banding với 8-bit 4:2:0
- Dithering là giải pháp nhẹ nhất, hiệu quả cao nhất cho streaming real-time
- Tăng bitrate là giải pháp đáng tin cậy nhất nhưng tốn bandwidth
- NVENC xử lý banding tốt hơn libx264 ở cùng bitrate nhờ spatial-aq
