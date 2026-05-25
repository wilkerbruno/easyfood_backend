# EasyFood API - Deploy no EasyPanel

## Passo a passo completo

---

### 1. Acesse o EasyPanel

Entre em: `https://easypanel.pontocomdesconto.com.br`

---

### 2. Crie um novo serviço

1. Clique em **"+ Create Service"**
2. Escolha **"App"**
3. Nome do serviço: `easyfood-api`
4. Clique em **"Create"**

---

### 3. Configure o Deploy

Na tela do serviço `easyfood-api`:

1. Vá na aba **"Source"**
2. Escolha **"Upload"**
3. Faça upload do arquivo `easyfood_backend.zip`
4. Build method: **"Dockerfile"**

---

### 4. Configure as variáveis de ambiente

Na aba **"Environment"**, adicione:

```
FLASK_ENV=production
JWT_SECRET_KEY=easyfood-jwt-super-secret-2024
SECRET_KEY=easyfood-secret-2024
```

---

### 5. Configure a porta

Na aba **"General"**:
- **Port:** `5000`
- **Proxy Port:** `80`

---

### 6. Configure o domínio

Na aba **"Domains"**:
- O EasyPanel vai gerar automaticamente algo como:
  `easyfood-api.pontocomdesconto.com.br`
- Habilite **HTTPS** (Let's Encrypt automático)

---

### 7. Deploy

Clique em **"Deploy"** e aguarde o build (2-5 minutos).

Verifique se funcionou acessando:
```
https://easyfood-api.pontocomdesconto.com.br/health
```

Deve retornar:
```json
{"status": "ok", "db": "connected"}
```

---

### 8. Atualize os apps com a URL

Após o deploy, edite nos apps React Native:

**EasyFoodCliente/src/api.ts:**
```typescript
export const SERVER_URL = 'https://easyfood-api.pontocomdesconto.com.br';
```

**EasyFoodRestaurante/src/api.ts:**
```typescript
export const SERVER_URL = 'https://easyfood-api.pontocomdesconto.com.br';
```

**EasyFoodAdmin/App.tsx:**
```typescript
const SERVER_URL = 'https://easyfood-api.pontocomdesconto.com.br';
```

Depois gere os APKs novamente.

---

### 9. Credenciais padrão

- **Admin:** admin@easyfood.com / admin@easyfood
- **Restaurantes:** admin@sabor.com / admin123

---

### Estrutura do projeto

```
easyfood_backend/
├── Dockerfile          ← Build para EasyPanel
├── wsgi.py             ← Entry point (Gunicorn)
├── requirements.txt    ← Dependências Python
├── backend/
│   ├── __init__.py     ← App factory Flask
│   ├── config.py       ← Configurações (DB, JWT)
│   ├── models/         ← Models SQLAlchemy
│   └── routes/         ← Rotas da API
├── static/             ← CSS, JS do frontend web
└── templates/          ← HTML (admin, restaurante, cliente)
```
