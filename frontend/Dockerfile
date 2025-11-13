# frontend/Dockerfile

# Stage 1: Install dependencies and build the Next.js application
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package.json and package-lock.json (or yarn.lock)
COPY package.json ./
COPY package-lock.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Build the Next.js application
# NEXT_PUBLIC_API_BASE_URL will be set at runtime via docker-compose
RUN npm run build

# Stage 2: Serve the Next.js application with a lightweight server
FROM node:20-alpine AS runner

WORKDIR /app

# Set environment variables for Next.js at runtime
# These variables are prefixed with NEXT_PUBLIC_ to be exposed to the browser
ENV NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Copy necessary files from the builder stage
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

# Expose the port Next.js runs on
EXPOSE 3000

# Command to run the Next.js application in production mode
CMD ["npm", "start"]
