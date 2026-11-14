# TRUBA VPN Operasyon ve Handover Notu

## Amaç

Bu belge, 14 Kasım 2026 tarihinde TRUBA/ARF erişimi sırasında teşhis edilen VPN
kararsızlığını, uygulanan geçici çözümü ve otomasyonun uyması gereken çalışma
kurallarını kaydeder. Yeni bir kişi veya ajan çalışmayı devraldığında önce bu notu
okumalıdır.

## Erişim özeti

- Yerel SSH aliası: `truba-arf`
- Uzak kullanıcı: `endemir`
- Login node/IP: `172.16.6.11` (`arf-ui1`)
- Uzak home: `/arf/home/endemir`
- TRUBA ağına erişim OpenVPN Connect üzerinden sağlanır.
- Parola, özel SSH anahtarı veya başka bir credential bu repoda tutulmaz.

## Teşhis edilen problem

OpenVPN tüneli başarılı biçimde kurulmasına rağmen yaklaşık iki dakikada bir veri
alamaz duruma geliyor. OpenVPN Connect bunu daha sonra `KEEPALIVE_TIMEOUT` olarak
kaydediyor, tüneli kapatıp birkaç saniye içinde yeniden kuruyor.

Gözlenen örnek döngüler:

- `23:19:44` bağlantı kuruldu; `23:21:34` `KEEPALIVE_TIMEOUT` oluştu.
- `23:21:37` bağlantı yeniden kuruldu; yaklaşık iki dakika sonra aynı davranış tekrarlandı.
- DNS filtreli profilde `23:30:58` bağlantı kuruldu; `23:32:58` timeout ve
  `23:33:02` yeniden bağlantı görüldü.

Problem hem ev Wi-Fi ağı hem de telefon hotspot'u üzerinde tekrarlandı. Eski OpenVPN
Connect 3.8.2 (6009) ve güncel 3.9.1 (6051) sürümlerinde de aynı davranış görüldü.
Bu nedenle ev modemi ve sabit internet hattı ana neden değildir. En güçlü adaylar
TRUBA'nın UDP VPN endpoint/profil davranışı ile istemci-network-extension etkileşimidir.

TRUBA'nın resmî profili şu endpoint'i kullanır:

```text
remote 193.140.99.241 1195 udp
```

TCP 1195 denemesi yanıt vermedi; doğrulanmış bir TCP fallback bulunmuyor.

## Normal internetin neden donduğu

TRUBA sunucusu bağlantı sırasında `172.16.0.1` DNS sunucusunu istemciye gönderiyor.
Tünel fiilen ölüp OpenVPN henüz timeout ilan etmediği aralıkta macOS DNS sorgularını
bu erişilemeyen sunucuya yönlendirmeye devam ediyordu. Bu nedenle VPN split-tunnel
olmasına rağmen tarayıcı ve diğer uygulamalar da geçici olarak donuyordu.

Ana internet rotası VPN'e alınmıyordu; sorun varsayılan rota değil, erişilemeyen VPN
DNS'inin öncelik kazanmasıydı.

## Uygulanan çözüm: DNS filtreli profil

TRUBA'nın resmî profilinin ayrı bir kopyasına yalnızca aşağıdaki seçenekler eklendi:

```text
pull-filter ignore "dhcp-option DNS"
pull-filter ignore "dhcp-option DOMAIN"
pull-filter ignore "register-dns"
```

Profil OpenVPN Connect'e `TRUBA-no-dns` adıyla içe aktarıldı. Orijinal profil silinmedi
ve değiştirilmedi. Profil dosyası yerel olarak Downloads klasöründe tutuldu; VPN
konfigürasyonu ve gömülü anahtar materyali repoya alınmamalıdır.

OpenVPN Connect logu filtrelerin çalıştığını doğruladı:

```text
Ignored due to pull-filter: [dhcp-option] [DNS] [172.16.0.1]
Ignored due to pull-filter: [register-dns]
```

macOS DNS çıktısında yalnızca normal ağ DNS'leri `8.8.8.8` ve `8.8.4.4` kaldı.
`172.16.6.11` rotasının VPN arayüzü üzerinden geçtiği ve `ssh truba-arf` erişiminin
sürdüğü ayrıca doğrulandı.

İki timeout döngüsü boyunca gözlenen sonuç:

- TRUBA SSH erişimi timeout penceresinde geçici olarak kesildi.
- Normal web erişimi kesintisiz kaldı.
- VPN yeniden bağlanınca SSH erişimi otomatik olarak geri geldi.

Bu çözüm tünel kopmasını düzeltmez; kopmanın kullanıcının normal internet kullanımını
etkilemesini engeller.

## Günlük kullanım

1. OpenVPN Connect'te `TRUBA-no-dns` profili kullanılmalıdır.
2. Ağ değiştirildikten sonra gerekirse VPN kapatılıp aynı profille yeniden bağlanmalıdır.
3. TRUBA iç DNS adları çözülmeyebilir. Bu proje `truba-arf` aliası ve
   `172.16.6.11` adresiyle çalıştığı için bu kabul edilebilir.
4. VPN'e ihtiyaç yokken bağlantı kapatılabilir. Slurm'a gönderilmiş işler VPN veya SSH
   bağlantısı kesilse de çalışmaya devam eder.
5. Profil uygulama içindeki `Import Profile` > `Upload File` ekranından alınmalıdır.
   Finder'dan `Open With` kullanımı OpenVPN Connect 3.9.1'de belge açılamadı hatası verdi.

## Otomasyon kuralları

VPN kararsızlığı giderilene kadar TRUBA otomasyonu şu kurallara uymalıdır:

- Uzun deneyler login shell içinde çalıştırılmamalı; Slurm job olarak gönderilmelidir.
- SSH ile yapılan idempotent işlemler sınırlı retry ve artan bekleme süresi kullanmalıdır.
- Job submission sonrası job ID hemen yerel provenance kaydına yazılmalıdır.
- Sonuç aktarımında yarım aktarımı sürdürebilen `rsync --partial` yaklaşımı tercih edilmelidir.
- SSH bağlantısının kesilmesi job başarısızlığı olarak yorumlanmamalı; durum daha sonra
  `squeue`, `sacct` ve sonuç manifestinden doğrulanmalıdır.
- Aynı komutun tekrar gönderilmesi duplicate job veya veri üzerine yazma yaratmamalıdır.
- Uzak taraftaki çalışma dizinleri deney ID'siyle benzersiz olmalıdır.
- Kritik küçük dosyalar yerelde checksum ile doğrulanmalıdır.

## Hızlı doğrulama komutları

Bağlantı ve rotayı kontrol etmek için:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 truba-arf hostname
route -n get 172.16.6.11
scutil --dns
```

Beklenen durum:

- SSH çıktısı `arf-ui1` olmalıdır.
- `172.16.6.11` rotası bir `utun` arayüzünden geçmelidir.
- DNS listesinde `172.16.0.1` bulunmamalıdır.

OpenVPN olayları şu yerel logdan incelenebilir:

```text
~/Library/Application Support/OpenVPN Connect/log/ovpn.log
```

Aranacak önemli ifadeler:

```text
KEEPALIVE_TIMEOUT
EVENT: RECONNECTING
EVENT: CONNECTED
Ignored due to pull-filter
```

## Kalıcı çözüm için sonraki adım

TRUBA desteğine zaman damgalı bir kayıt gönderilmelidir. Raporda şu kanıtlar bulunmalıdır:

- İki farklı ağda aynı timeout davranışı.
- OpenVPN Connect 3.8.2 ve 3.9.1'de aynı sonuç.
- Yaklaşık iki dakikalık düzenli `KEEPALIVE_TIMEOUT` döngüsü.
- Resmî UDP endpoint ve port bilgisi.
- İlgili log kesitleri; credential veya özel anahtarlar eklenmemelidir.

Dış destek e-postası kullanıcı onayı olmadan gönderilmemelidir. Destek kalıcı bir çözüm
sağlayana kadar `TRUBA-no-dns` profili ve retry-tolerant Slurm akışı kullanılacaktır.
