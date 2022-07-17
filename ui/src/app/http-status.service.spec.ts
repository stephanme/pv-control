import { HttpClient, HTTP_INTERCEPTORS } from '@angular/common/http';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { HttpStatusInterceptor, HttpStatusService } from './http-status.service';

describe('HttpStatusService', () => {
  let service: HttpStatusService;
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let busy = false;
  let httpErr: string | undefined;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule
      ],
      providers: [
        {
          provide: HTTP_INTERCEPTORS,
          useClass: HttpStatusInterceptor,
          multi: true,
        }
      ]
    });
    service = TestBed.inject(HttpStatusService);
    busy = false;
    service.busy().subscribe(b => busy = b);
    httpErr = undefined;
    service.httpError().subscribe(e => httpErr = e);
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should report busy requests', () => {
    expect(busy).toBe(false);
    http.get('/').subscribe(() => {
      expect(busy).toBe(true);
    });

    const req = httpMock.expectOne('/');
    req.flush({});

    expect(busy).toBe(false);
    expect(httpErr).toBeUndefined();
  });

  it('should report http errors', () => {
    http.get('/').subscribe({ next: () => { }, error: () => { } });
    const req = httpMock.expectOne('/');
    req.flush('', {
      status: 500,
      statusText: 'Internal Server Error'
    });

    expect(busy).toBe(false);
    expect(httpErr).toBe('HTTP 500 Internal Server Error - GET /');
  });
});
