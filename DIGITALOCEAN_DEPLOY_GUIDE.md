# 🚀 **DigitalOcean + Docker 배포 가이드**

> **당신이 해야 할 일만 정리했습니다.**

---

## ⏱️ **예상 시간: 30분**

```
1️⃣ DigitalOcean 계정 생성: 5분
2️⃣ Droplet 생성: 5분
3️⃣ SSH 접속: 2분
4️⃣ 봇 배포: 10분
5️⃣ TradingView 설정: 5분
6️⃣ 테스트: 3분
```

---

## 🎯 **Step 1: DigitalOcean 계정 생성 (5분)**

### **1️⃣ 웹사이트 방문**

```
https://www.digitalocean.com
```

### **2️⃣ "Sign Up" 클릭**

```
이메일 입력
비밀번호 입력
회원가입
```

### **3️⃣ 결제 정보 입력**

```
신용카드 정보 입력
(월 $5부터 시작)
```

### **4️⃣ 확인 메일 클릭**

```
이메일에서 "Verify your email" 클릭
```

**완료! ✅**

---

## 🎯 **Step 2: Droplet 생성 (5분)**

### **1️⃣ Dashboard에서 "Create" 클릭**

```
좌측 메뉴 → "Create" → "Droplets"
```

### **2️⃣ 설정**

```
Choose an image:
  ☑️ Ubuntu (Latest - 22.04 x64)

Choose a size:
  ☑️ Basic $5/month (1GB RAM, 1 vCPU)

Choose a datacenter region:
  ☑️ Singapore (또는 가까운 지역)

Authentication:
  ☑️ Password (비밀번호로 설정)

Hostname:
  ☑️ ib-trading-bot

✓ Create Droplet 클릭
```

### **3️⃣ 대기 (2-3분)**

```
"Your Droplet is ready!" 메시지 대기
```

**완료! ✅**

---

## 🎯 **Step 3: SSH 접속 (2분)**

### **1️⃣ Droplet IP 확인**

```
Dashboard에서 생성된 Droplet 클릭
IP Address 확인 (예: 123.45.67.89)
```

### **2️⃣ Windows에서 접속**

```
PowerShell을 열고:
ssh root@123.45.67.89
(IP 주소를 당신의 IP로 바꾸세요)

비밀번호 입력 (DigitalOcean에서 받은 메일)
```

또는 **PuTTY** 사용:

```
Host: 123.45.67.89
Port: 22
Connection type: SSH
Open 클릭
로그인: root
비밀번호 입력
```

**완료! ✅**

---

## 🎯 **Step 4: 봇 배포 (10분)**

SSH 접속 후 다음 명령어 실행:

### **1️⃣ Docker 설치**

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker root
```

### **2️⃣ Docker Compose 설치**

```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker-compose --version
```

### **3️⃣ 봇 코드 다운로드**

```bash
cd /root
git clone https://github.com/YOUR_USERNAME/ib-trading-bot.git
cd ib-trading-bot
```

또는 파일을 직접 업로드:

```bash
# SCP로 업로드 (Windows PowerShell):
scp -r C:\Users\palet\Desktop\Factory\ib-trading-bot root@123.45.67.89:/root/
```

### **4️⃣ .env 파일 확인**

```bash
nano .env
```

다음이 있는지 확인:

```
WEBHOOK_SECRET=
WEBHOOK_PORT=8000
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

저장: `Ctrl+X` → `Y` → `Enter`

### **5️⃣ Docker 실행**

```bash
docker-compose up -d
```

대기 (2-3분)

### **6️⃣ 상태 확인**

```bash
docker-compose ps
```

결과:

```
NAME                STATUS
api                 Up (healthy)
worker              Up
telegram            Up
db                  Up (healthy)
redis               Up (healthy)
```

모두 `Up`이면 성공! ✅

---

## 🎯 **Step 5: TradingView 웹훅 URL 설정 (5분)**

### **1️⃣ 당신의 Droplet IP 확인**

```
DigitalOcean Dashboard에서 IP: 123.45.67.89
```

### **2️⃣ TradingView 알림 설정**

**알림 탭에서 웹훅 URL:**

```
http://123.45.67.89:8000/webhook
```

**Secret (webhook secret):**

```
MySecret123456
```

### **3️⃣ 저장**

```
"생성" 버튼 클릭
```

**완료! ✅**

---

## 🎯 **Step 6: 테스트 (3분)**

### **1️⃣ TradingView에서 신호 발송**

```
알림 설정이 완료되면
다음 조건 충족 시 신호 자동 발송
```

### **2️⃣ Telegram에서 확인**

```
Telegram에서 메시지 수신 확인
```

### **3️⃣ 로그 확인 (선택)**

```bash
docker-compose logs api
docker-compose logs worker
```

---

## 🔧 **트러블슈팅**

### **웹훅 신호가 안 와요**

```bash
# API 로그 확인
docker-compose logs api -f

# 포트 확인
docker-compose ps
```

### **데이터베이스 에러**

```bash
# DB 재시작
docker-compose restart db
```

### **Redis 에러**

```bash
# Redis 재시작
docker-compose restart redis
```

### **봇 다시 시작**

```bash
docker-compose restart worker
docker-compose restart telegram
```

---

## 📊 **월별 비용**

```
DigitalOcean Droplet: $5/월
도메인 (선택): $3-12/월
합계: $5/월 (또는 $8-17/월 with 도메인)
```

---

## ✅ **체크리스트**

- [ ] DigitalOcean 계정 생성
- [ ] Droplet 생성됨
- [ ] SSH로 접속 확인
- [ ] Docker 설치됨
- [ ] 봇 배포됨
- [ ] 모든 컨테이너 Running 상태
- [ ] TradingView 웹훅 URL 설정됨
- [ ] Telegram 메시지 수신 확인됨

---

## 🚀 **이제 시작하세요!**

```
1. DigitalOcean 가입: https://www.digitalocean.com
2. Droplet 생성
3. SSH 접속
4. 위의 명령어 실행
5. 완료!
```

---

**모든 것이 준비되었습니다!** 🎉

당신의 봇이 24시간 자동으로 실행될 것입니다! ✨
