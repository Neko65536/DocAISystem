前端启动：
cd extended-frontend
npm install
npm run dev

后端启动：
cd src
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
