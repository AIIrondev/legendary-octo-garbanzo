from app import app
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['username'] = 'admin'
        sess['admin'] = True
    resp = client.get('/terminplan')
    print("Status:", resp.status_code)
