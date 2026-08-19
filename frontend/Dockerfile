# Node 20 LTS, not 18: the lint toolchain added in FIX-001 declares
# `engines: node ^20.19 || ^22.13 || >=24` (ESLint 10), so a node:18 image
# could install it only with an EBADENGINE warning and could not run it.
# Node 18 also reached end of life in April 2025.
FROM node:20-alpine

WORKDIR /app

# `package*.json` picks up package-lock.json, which is versioned: `npm ci`
# installs exactly the resolved tree instead of re-resolving `^` ranges on
# every build, so the image matches the machine the code was tested on.
COPY package*.json ./

RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
