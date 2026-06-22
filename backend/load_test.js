import http from 'k6/http';
import { check } from 'k6';

const img = open('./test_cropped.jpg', 'b');

export const options = {
    vus: 50,
    duration: '30s',
};

export default function () {
    const data = {
        file: http.file(img, 'test.jpg', 'image/jpeg'),
        expert_id: 'test_user',
    };

    const res = http.post('http://localhost:8080/api/upload', data);

    check(res, {
        'status is 200': (r) => r.status === 200,
    });
}