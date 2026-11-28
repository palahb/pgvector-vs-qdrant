# Açık maddeler (27 Kasım 2026)

## A. Sizin yapmanız gerekenler (ben yapamam, yapmamam gerekir)

| Ne | Neden sizde | Ne zamana kadar |
|---|---|---|
| **Overleaf'te derleme** (`paper/OVERLEAF.md`) | Burada TeX yok, makale hiç derlenmedi. Geniş tablolar, uzun `\texttt` adları ve `figure*` tek sütunda kontrol edilmeli | 14 Aralık |
| **Information Systems "Guide for Authors"ı bir tarayıcıda okumak** (`docs/JOURNAL_CHECK.md`) | ScienceDirect sayfası bana 403 verdi. Kapsam, makale türü, uzunluk sınırı, highlights/graphical abstract, veri politikası, hakem modeli doğrulanmadı; hiçbirini hafızadan yazmadım | Gönderimden önce |
| **Yapay zekâ beyanını onaylamak** (`paper/ai_use_statement.md`; metne Elsevier'in istediği yere, kaynakçanın üstüne konuldu) | Son iki cümle yazarların taahhüdü. Her yazar metni gerçekten okumuş olmalı. Hocanın Claude/Gemini ile hazırladığı değerlendirme belgelerinin beyanda anılıp anılmayacağı hocanın kararı | 14 Aralık |
| **Beyanları doğrulamak:** rakip çıkar beyanı, fonlama cümlesi, veri/kod erişilebilirliği ("ham sonuçları talep üzerine sağlarız"), CRediT yazar katkıları, sorumlu yazar | Bunlar yazarların beyanı; metinde taslak olarak duruyor (`% AUTHORS:` yorumları), CRediT ve sorumlu yazar henüz yok | Gönderimden önce |
| **Ham sonuçlar (yaklaşık 3 GB) nerede durur?** | Depoda değil; manifestlerde özetleri var. Bir arşive (DOI ile) koymak yazarların kararı | Gönderimden önce |
| Hocaya cevap maili | Göndermek sizde. Taslak: `docs/MAIL_HOCA_TESLIM.md` | İstediğiniz zaman |
| pgvector issue'su | Gönderilmedi. Tekrar üretici betik **hiç çalıştırılmadı**; çalıştırılmadan gönderilmemeli (`docs/PGVECTOR_ISSUE_DRAFT.md`) | İsteğe bağlı |
| pgvector 4G kolları | Varsayılan "tamamlanmadı" olarak raporlanıyor; koşturmak 3 saatten uzun ve kuyrukta saatler bekler (`docs/E10_MEMORY_DECISION.md`) | 1 Aralık (karar) |

## B. Bilinen sınırlar (makalede de yazılı)

* Makale derlenmedi; yapısı betikle denetlendi (dengeli ortamlar, tanımlı atıflar, kullanılmayan etiket yok, `\todo` yok, 21 kaynak hepsi atıflı).
* Otomatik denetlenmeyen sayılar: üreteci olmayan bölümlerin nesir içindeki sayıları (başlık sayıları ve 9 tablonun hücreleri hariç), `tab:laptop`, `tab:caps`'in 4 GB satırı. `docs/TAG_POLICY.md`.
* E1–E5 (2026-11-14 arşivi) üreten commit ve seed taşımaz; `baseline_2026-11-14.json` ve şekil yeniden üretimiyle bağlı.
* E22'nin ilk koşusu kayıt olarak duruyor; analizi, onu üreten commit'in araçlarıyla yeniden üretiliyor (`936736e`).
* Qdrant'ın depolama boyutu aynı yapılandırmanın build'leri arasında yaklaşık üçte bir oynuyor, nedeni bulunamadı; `int8` için depolama oranı verilmedi.
* Mesafe sayısı ölçülemedi (sayaç yok, root yok, eBPF yok); önbellek-ıskalama vekili pgvector'ün blok sayacıyla 1% içinde doğrulandı (`E19`).
* Kullandığımız `hamsi` düğümlerinde NVMe yok (bir düğümde doğrulandı); **diğer bölümler (orfoz, barbun, smp) bakılmadı**. Hoca "TRUBA'da NVMe kullanabilirsin" demişti; bu doğrulanana kadar depolamaya bağlı her sonuç "HDD, en kötü durum".
* nDCG: 63 sorgu, korpus yargılı ilgili belgelerin %0,7'sini taşıyor; oranlar kesin aramaya göre, mutlak etkinlik değil.
* Şekil: yeni deneyler (E19–E23) için şekil üretilmedi, yalnızca tablolar var. İsterseniz E22 (yüke karşı p99) ve E19 (kategori başına döngü) için iki şekil eklenebilir.

## C. Planın dışında bırakılanlar (hocanın kararı: gelecek iş)

Filtreli ve hibrit arama, karma okuma-yazma, 16+ çekirdek, pgvectorscale/VectorChord, ikinci gömme modeli, 10M ölçek, NVMe, uzun ömürlü bağlantılarla açık döngü.
