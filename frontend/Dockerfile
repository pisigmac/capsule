FROM node:20-alpine

WORKDIR /app

# Install dependencies first for layer caching
COPY package.json ./
RUN npm install

# Copy application files
COPY . .

EXPOSE 5173

# Start Vite dev server exposed to all interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
