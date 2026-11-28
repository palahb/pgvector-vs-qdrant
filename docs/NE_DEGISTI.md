# Ne değişti: ders raporundan makale taslağına (27 Kasım 2026)

Bu belge hocaya gidecek özetin gerekçesidir. Her satırın kanıtı depoda: manifest (`data-manifests/`), analiz (`results/derived/`), makale bölümü.

## 1. Çerçeve

* Başlık "RAG iş yükleri"nden **"Where Vector Search Benchmarks Go Wrong: A Controlled Comparison of pgvector and Qdrant"**a döndü (hocanın 17 Kasım onayı: filtresiz ANN araması).
  Makale artık "hangi sistem hızlı" sıralaması değil, bir karşılaştırmanın nasıl yanlış gittiğini ve hangi denetimlerle önlendiğini anlatıyor.
* Şablon Elsevier `elsarticle` (hedef: Information Systems; ACM sürümü `paper/alt/` altında yedek). **Derlenmedi** (TeX yok), Overleaf'te derlenecek: `paper/OVERLEAF.md`.

## 2. Referee maddeleri ve yeni kanıt

| Madde | Durum | Kanıt |
|---|---|---|
| M1/M2 gecikme ve CPU, segment sayısı | Yapıldı | E6, E8. Gecikme oranı 3,1–3,4× (4 segment), CPU oranı yaklaşık 1,4×; 8 segmentte yaklaşık eşit |
| **Nedensel analiz** (hocanın 17 Kasım isteği) | Yapıldı, sınırlı | **E19**: pgvector daha az vektör okuyor (5,2 bin, Qdrant 6,9–8,9 bin) ama okuma başına 2,3× döngü harcıyor; döngülerinin %49'u mesafe ve eleman yükleme dışında (buffer manager %25, adsız `postgres` adresleri %16). Mesafe sayısı ölçülemedi (sayaç yok, root yok): vekil ve üst sınırlar, `perf` yalnızca kullanıcı alanı |
| M3/M4 build | Kısmen | E9: sonuç yükleme biçimine bağlı; NVMe hamsi (2 düğüm) ve smp'de yok, **orfoz'da var** (orfoz183, Micron 7450); TRUBA dokümanı "tüm sunucularda /tmp NVMe" diyor, ayrıntı `docs/STORAGE_CHECK.md`'de, barbun bekliyor |
| M5 bellek | Yapıldı (4G pgvector hariç) | E10, ölçüt karşılaştırması `docs/E10_MEMORY_DECISION.md` |
| M6 tutarsızlıklar | Yapıldı | `tab:sources` (her tablo için `ef`, node, build), `tab:commits` |
| M7 eşleşmiş recall | Yapıldı | Verim tam 0,95'e CPU eğrisiyle düzeltildi: 1M'de pgvector +%13,9, Qdrant +%10,6, oran 1,64→1,59 |
| M8 kapalı döngü | Açık döngü yapıldı, çekirdek ölçeği gelecek iş | **E22**: %80 yükte pgvector p99'u Qdrant'ın yaklaşık 2×'i; pgvector %95'te oturmadı |
| M9/M10 kapsam | Kapsam daraltıldı | filtreli/hibrit, karma okuma-yazma, ikinci model, 10M gelecek iş listesinde |
| M11 motor süreleri | Yapıldı | E19 + E7 |
| M12 planner | Yapıldı; **upstream raporu gönderilmedi** | E17; `docs/PGVECTOR_ISSUE_DRAFT.md` (tekrar üretici betik çalıştırılmadı) |

## 3. Hocanın geri çağırdığı beş madde

1. Nedensel analiz — **E19** (yukarıda).
2. `halfvec` ve `int8` — **E20**: `halfvec` indeksi 1/3 boyutta, hız ve recall'da ölçülebilir kayıp yok; `int8` Qdrant'ı sorgu başına 1,6× hızlandırıyor ama depolamayı küçültmüyor (Qdrant depolaması ortalama 5,2 GB'tan 6,4 GB'a çıkıyor; build'ler arası değişim büyük olduğu için oran verilmedi). "pgvector iki kat yer kaplıyor" artık "32 bit yerleşimin özelliği".
3. PgBouncer — **E21**: p99'u yaklaşık yarıya indiriyor, verimi artırmıyor, bu iş yükünde bir kuyruk gecikmesi denetimi.
4. Minimal open-loop — **E22**.
5. nDCG@10 — **E23**: 1M korpus, yargılı ilgili belgelerin yalnızca %0,72'sini kapsıyor; kural ölçümden önce yazıldı (`docs/E23_GATE.md`), karar "yalnızca duyarlılık analizi". Recall 0,95'te yaklaşık sonuç, kesin aramanın nDCG@10'unun %98'ini koruyor.

## 4. Kendi hatalarımız (bulundu ve düzeltildi, makalede ve kayıtta yazılı)

* `hnsw.ef_search > 1000` pgvector'de sessizce yok sayılıyor (varsayılan 40 kalıyor): E6/E8'deki `ef=1024` satırları bu yüzden dışarıda bırakıldı.
* Zhang vd. makalesi pgvector'ü değil PASE'i inceliyor; metin düzeltildi.
* "Yaklaşık 250×" yerine aynı koşullarda ölçülen **218×**; "2,4–3,8×" yerine **3,0–3,8×**.
* Eski 300 sorgulu bellek iddiası geri çekildi, yerine tam sorgu seti geldi.
* **Gönderdiğimiz ilk mailde "qrels elimizde" yazıyordu; doğrulanmamıştı.** Qrels diskte yoktu. Sonradan indirildi ve ölçüldü (`docs/HOCA_CEVAP_17_KASIM.md`).
* PgBouncer kancası ilk yazıldığında iki kusur taşıyordu (oturum `SET`'i havuzdan geçmiyor, havuzcu CPU'su yanlış süreçten okunuyor); çalıştırılmadan önce bulundu.
* E22'nin ilk koşusunda pgvector için başlangıç birikimi; ikinci koşuda "kararlı" ölçütü verilerden sonra sıkılaştırıldı. İkisi de makalede ve `docs/E22_DESIGN.md`'de açık.
* **Son doğrulama turunda** tablo hücresi denetimi, yuvarlanmış göstergeden kopyalanmış üç değer (2,01→2,00; 571→570; 3,94→3,93) ve yuvarlanmış hücrelerden bölünmüş bir oran (2,4→2,3) buldu; düzeltildi.

## 5. Tekrar üretilebilirlik

* Her deneyin manifesti: üreten commit, job'lar, node'lar, dosya özetleri (`tab:commits`).
* Etiketler: `harness-v1` (son harness değişikliği), `analysis-v2` (analiz araçları). `make verify-paper`: 18 analizi ham sonuçtan yeniden üretir, üreteçle yazılmış bölümleri, 27 başlık sayıyı ve 9 tablonun hücrelerini denetler, testleri çalıştırır; etikette 30 adımın hepsi geçiyor.
* **Sınır:** üreteci olmayan bölümlerin nesir içindeki sayıları (başlık sayıları hariç) elle kopyalanmıştır ve otomatik denetlenmez; E1–E5 komit ve seed taşımaz.
