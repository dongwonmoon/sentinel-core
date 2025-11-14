import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(function (_a) {
    var mode = _a.mode;
    return ({
        plugins: [react()],
        server: {
            port: 5173,
            proxy: {
                "/api": {
                    target: resolveApiTarget(mode),
                    changeOrigin: true,
                    secure: false,
                },
            },
        },
    });
});
function resolveApiTarget(mode) {
    var _a;
    if (mode === "development") {
        return ((_a = process.env) === null || _a === void 0 ? void 0 : _a.VITE_API_BASE_URL) || "http://localhost:8000";
    }
    return "http://localhost:8000";
}
