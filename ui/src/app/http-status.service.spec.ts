import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { HttpStatusService, statusInterceptor } from './http-status.service';

describe('HttpStatusService', () => {
  let service: HttpStatusService;
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let httpErr: string | undefined;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [],
      providers: [
        provideHttpClient(withInterceptors([statusInterceptor])), 
        provideHttpClientTesting(),
      ]
    });
    service = TestBed.inject(HttpStatusService);
    httpErr = undefined;
    service.httpError().subscribe(e => httpErr = e);
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should report busy requests', () => {
    expect(service.busy()).toBe(false);
    http.get('/').subscribe(() => {
      expect(service.busy()).toBe(true);
    });

    const req = httpMock.expectOne('/');
    req.flush({});

    expect(service.busy()).toBe(false);
    expect(httpErr).toBeUndefined();
  });

  it('should report http errors', () => {
    http.get('/').subscribe({ next: () => { }, error: () => { } });
    const req = httpMock.expectOne('/');
    req.flush('', {
      status: 500,
      statusText: 'Internal Server Error'
    });

    expect(service.busy()).toBe(false);
    expect(httpErr).toBe('HTTP 500 Internal Server Error - GET /');
  });
});
