import app from './mock-api.js';

const PORT = 3001;

app.listen(PORT, () => {
  console.log(`[Mock API] listening on port ${PORT}`);
});
