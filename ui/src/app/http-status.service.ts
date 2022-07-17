import { HttpHandler, HttpRequest, HttpEvent, HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, Subject } from 'rxjs';
import { tap, finalize } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class HttpStatusService {
  private busyCnt = 0;
  private busySubject = new BehaviorSubject<boolean>(false);
  private httpErrorSubject = new Subject<string>();

  constructor() { }

  incBusy(): void {
    this.busyCnt++;
    if (this.busyCnt === 1) {
      this.busySubject.next(true);
    }
  }

  decBusy(): void {
    this.busyCnt--;
    if (this.busyCnt === 0) {
      this.busySubject.next(false);
    }
  }

  notifyHttpError(msg: string): void {
    this.httpErrorSubject.next(msg);
  }

  busy(): Observable<boolean> {
    return this.busySubject.asObservable();
  }

  httpError(): Observable<string> {
    return this.httpErrorSubject.asObservable();
  }
}

@Injectable()
export class HttpStatusInterceptor {
  constructor(private httpStatusService: HttpStatusService) { }

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    this.httpStatusService.incBusy();

    return next.handle(req).pipe(
      tap({
        next: () => null,
        error: errEvent => {
          let msg: string;
          if (errEvent instanceof HttpErrorResponse) {
            msg = `HTTP ${errEvent.status} ${errEvent.statusText} - ${req.method} ${req.url}`;
          } else {
            msg = `Unknown error - ${req.method} ${req.url}`;
          }
          console.log(`Http request failed: ${msg}`);
          this.httpStatusService.notifyHttpError(msg);
        }
      }),
      finalize(() => {
        // is also called on canceled requests
        this.httpStatusService.decBusy();
      })
    );
  }
}
