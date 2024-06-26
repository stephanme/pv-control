import { HttpRequest, HttpEvent, HttpErrorResponse, HttpHandlerFn } from '@angular/common/http';
import { inject, Injectable, signal, WritableSignal } from '@angular/core';
import { Observable } from 'rxjs';
import { tap, finalize } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class HttpStatusService {
  private busyCnt = 0;

  private _busy = signal(false);
  busy = this._busy.asReadonly();
  public readonly httpError: WritableSignal<{errmsg: string} | null> = signal(null);

  incBusy(): void {
    this.busyCnt++;
    if (this.busyCnt === 1) {
      this._busy.set(true);
    }
  }

  decBusy(): void {
    this.busyCnt--;
    if (this.busyCnt === 0) {
      this._busy.set(false);
    }
  }

  notifyHttpError(msg: string): void {
    // wrap errmsg into object to notify about the same errmsg as well
    this.httpError.set({errmsg: msg});
  }
}

// eslint-disable-next-line  @typescript-eslint/no-explicit-any
export function statusInterceptor(req: HttpRequest<any>, next: HttpHandlerFn): Observable<HttpEvent<any>> {
  const statusService = inject(HttpStatusService);
  statusService.incBusy();

  return next(req).pipe(
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
        statusService.notifyHttpError(msg);
      }
    }),
    finalize(() => {
      // is also called on canceled requests
      statusService.decBusy();
    })
  );
}
