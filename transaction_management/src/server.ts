import express from 'express';
import { self } from './config/sites.js';
import { pool } from './config/db.js';

const app = express();
app.use(express.json());

app.get('/internal/health', async (_req, res) => {
  try {
    await pool.query('SELECT 1');
    res.json({ node: self.id, role: self.role, fragment: self.fragment, db: 'up' });
  } catch {
    res.status(503).json({ node: self.id, db: 'down' });
  }
});

const port = Number(process.env.PORT ?? 8000);
app.listen(port, () => {
  console.log(`[${self.id}] ${self.role} listening on :${port}`);
});
